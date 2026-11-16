from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.ai import get_llm_http, get_session
from careerflow.application.ai.client import AiClient
from careerflow.domain.ai.config import AiConfig
from careerflow.domain.ai.ports import (
    AiProviderError,
    AiRateLimitError,
    AiTimeoutError,
    CompletionRequest,
    LlmProvider,
)
from careerflow.infrastructure.database.models import Base
from careerflow.infrastructure.llm.factory import build_provider
from careerflow.infrastructure.llm.http_providers import (
    AnthropicProvider,
    LlmHttpResponse,
    OpenAICompatibleProvider,
)
from careerflow.main import create_app
from careerflow.settings import get_settings

KEY = "sk-live-VERYSECRET-0123456789"

OPENAI_OK = {
    "model": "gpt-test-2026",
    "choices": [{"message": {"role": "assistant", "content": '{"echoed": "hi"}'}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
}
ANTHROPIC_OK = {
    "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": '{"echoed": "hi"}'}],
    "usage": {"input_tokens": 21, "output_tokens": 7},
}


class FakeLlmHttp:
    def __init__(self, response: LlmHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(self, url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float) -> LlmHttpResponse:
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def ok(payload: dict[str, Any]) -> FakeLlmHttp:
    return FakeLlmHttp(LlmHttpResponse(200, json.dumps(payload)))


def request(**kw: Any) -> CompletionRequest:
    return CompletionRequest(system="sys", user="usr", prompt_key="echo_test", prompt_version="v1", **kw)


# --- OpenAI-compatible --------------------------------------------------------------------------


def test_openai_compatible_request_shape_and_result() -> None:
    http = ok(OPENAI_OK)
    provider = OpenAICompatibleProvider("https://api.example.com/v1/", "gpt-test", KEY, http)
    result = provider.complete(request(timeout_seconds=12))
    call = http.calls[0]
    assert call["url"] == "https://api.example.com/v1/chat/completions"
    assert call["headers"] == {"Authorization": f"Bearer {KEY}"}
    assert call["timeout"] == 12
    assert call["body"]["model"] == "gpt-test"
    assert call["body"]["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    assert call["body"]["response_format"] == {"type": "json_object"}
    assert (result.text, result.provider, result.model) == ('{"echoed": "hi"}', "openai_compatible", "gpt-test-2026")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 5)


def test_openai_compatible_without_key_or_json_mode() -> None:
    http = ok(OPENAI_OK)
    provider = OpenAICompatibleProvider("http://localhost:11434/v1", "llama3", "", http, name="ollama")
    provider.complete(request(json_output=False))
    assert http.calls[0]["headers"] == {} and "response_format" not in http.calls[0]["body"]
    assert provider.name == "ollama"


def test_openai_compatible_requires_endpoint_and_model() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        OpenAICompatibleProvider("", "m")
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleProvider("https://x/v1", "")


# --- Anthropic ----------------------------------------------------------------------------------


def test_anthropic_request_shape_and_result() -> None:
    http = ok(ANTHROPIC_OK)
    provider = AnthropicProvider("claude-sonnet-5-5", KEY, http=http)
    result = provider.complete(request())
    call = http.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"] == {"x-api-key": KEY, "anthropic-version": "2023-06-01"}
    assert call["body"] == {
        "model": "claude-sonnet-5-5", "max_tokens": 4096, "system": "sys",
        "messages": [{"role": "user", "content": "usr"}],
    }  # fmt: skip
    assert (result.text, result.provider) == ('{"echoed": "hi"}', "anthropic")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (21, 7)


def test_anthropic_requires_a_key_and_ignores_non_text_blocks() -> None:
    with pytest.raises(ValueError, match="AI_API_KEY"):
        AnthropicProvider("m", "")
    mixed = {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    assert AnthropicProvider("m", KEY, http=ok(mixed)).complete(request()).text == "ab"
    with pytest.raises(AiProviderError, match="no text"):
        AnthropicProvider("m", KEY, http=ok({"content": []})).complete(request())


# --- shared contract: errors and secrets, both providers -------------------------------------------

PROVIDERS = {
    "openai": lambda http: OpenAICompatibleProvider("https://api.example.com/v1", "m", KEY, http),
    "anthropic": lambda http: AnthropicProvider("m", KEY, http=http),
}


@pytest.mark.parametrize("make", PROVIDERS.values(), ids=PROVIDERS.keys())
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (LlmHttpResponse(429, "slow"), AiRateLimitError),
        (LlmHttpResponse(401, f"bad key {KEY}"), AiProviderError),
        (LlmHttpResponse(403, "forbidden"), AiProviderError),
        (LlmHttpResponse(500, f"oops {KEY}"), AiProviderError),
        (LlmHttpResponse(200, "<html>not json</html>"), AiProviderError),
        (LlmHttpResponse(200, "[1, 2]"), AiProviderError),
        (LlmHttpResponse(200, "{}"), AiProviderError),
        (AiTimeoutError("slow"), AiTimeoutError),
    ],
)
def test_failures_are_normalised_and_never_leak_the_key(make: Any, response: Any, expected: type[Exception]) -> None:
    provider: LlmProvider = make(FakeLlmHttp(response))
    with pytest.raises(expected) as info:
        provider.complete(request())
    assert KEY not in str(info.value)


@pytest.mark.parametrize("make", PROVIDERS.values(), ids=PROVIDERS.keys())
def test_providers_work_through_the_structured_client(make: Any) -> None:
    class Echo(BaseModel):
        echoed: str

    payload = OPENAI_OK if make is PROVIDERS["openai"] else ANTHROPIC_OK
    result = AiClient(make(ok(payload))).run("echo_test", {"text": "hi"}, Echo)
    assert result.value.echoed == "hi" and result.usage.input_tokens and result.attempts == 1


# --- factory ----------------------------------------------------------------------------------------


def test_factory_builds_each_provider_with_defaults() -> None:
    def cfg(**kw: object) -> AiConfig:
        base: dict[str, object] = {"enabled": True, "provider": "x", "model": "m", "endpoint": "", "api_key": KEY}
        return AiConfig(**{**base, **kw})  # type: ignore[arg-type]

    assert build_provider(cfg(provider="openai_compatible")).name == "openai_compatible"
    assert build_provider(cfg(provider="ollama", api_key="")).name == "ollama"
    assert build_provider(cfg(provider="anthropic", model="")).model == "claude-sonnet-5-5"
    assert build_provider(cfg(provider="anthropic", enabled=False)).name == "disabled"
    assert KEY not in repr(cfg())  # the key is excluded from repr/log output


# --- configuration API ------------------------------------------------------------------------------


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, dict[str, FakeLlmHttp | None]]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    holder: dict[str, FakeLlmHttp | None] = {"http": None}

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_llm_http] = lambda: holder["http"]
    yield TestClient(app), holder
    get_settings.cache_clear()


def test_config_never_returns_the_key_only_whether_one_is_set(
    api: tuple[TestClient, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    assert client.get("/api/v1/ai/config").json()["api_key_set"] is False
    monkeypatch.setenv("AI_API_KEY", KEY)
    get_settings.cache_clear()
    response = client.get("/api/v1/ai/config")
    assert response.json()["api_key_set"] is True
    assert KEY not in response.text
    put = client.put("/api/v1/ai/config", json={"enabled": True, "provider": "anthropic", "model": "claude-x"})
    assert put.status_code == 200 and KEY not in put.text and put.json()["api_key_set"] is True
    assert KEY not in client.get("/api/v1/ai/status").text
    assert KEY not in client.post("/api/v1/ai/test").text


def test_config_rejects_attempts_to_store_a_secret(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    response = client.put("/api/v1/ai/config", json={"enabled": True, "provider": "anthropic", "api_key": KEY})
    assert response.status_code == 422
    assert KEY not in response.text
    assert client.put("/api/v1/ai/config", json={"enabled": True, "provider": "skynet"}).status_code == 422


def test_saved_selection_overrides_environment_and_can_be_reset(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    assert client.get("/api/v1/ai/config").json()["source"] == "environment"
    saved = client.put("/api/v1/ai/config", json={"enabled": True, "provider": "ollama", "model": "llama3", "endpoint": "http://gpu:11434/v1"}).json()
    assert (saved["provider"], saved["model"], saved["endpoint"], saved["source"]) == ("ollama", "llama3", "http://gpu:11434/v1", "saved")
    assert client.get("/api/v1/ai/status").json() == {"enabled": True, "provider": "ollama", "model": "llama3", "available": True}
    reset = client.delete("/api/v1/ai/config").json()
    assert reset["source"] == "environment" and reset["enabled"] is False
    assert "anthropic" in reset["providers"] and reset["providers"]["anthropic"]["needs_key"] is True


def test_connectivity_test_reports_success_and_readable_failures(api: tuple[TestClient, Any]) -> None:
    client, holder = api
    assert client.post("/api/v1/ai/test").json() == {"ok": False, "provider": "disabled", "model": "none", "latency_ms": None, "error": "AI is disabled"}

    client.put("/api/v1/ai/config", json={"enabled": True, "provider": "openai_compatible", "model": "m", "endpoint": "https://api.example.com/v1"})
    holder["http"] = ok(OPENAI_OK)
    good = client.post("/api/v1/ai/test").json()
    assert good["ok"] is True and good["provider"] == "openai_compatible" and good["latency_ms"] is not None and good["error"] is None

    for response, fragment in (
        (LlmHttpResponse(401, "no"), "rejected the credentials"),
        (LlmHttpResponse(429, ""), "rate limit"),
        (LlmHttpResponse(500, ""), "HTTP 500"),
        (AiTimeoutError("provider did not answer within 20.0s"), "did not answer"),
    ):
        holder["http"] = FakeLlmHttp(response)
        bad = client.post("/api/v1/ai/test").json()
        assert bad["ok"] is False and fragment in bad["error"]

    client.put("/api/v1/ai/config", json={"enabled": True, "provider": "anthropic", "model": "m"})  # no key in env
    missing = client.post("/api/v1/ai/test").json()
    assert missing["ok"] is False and "AI_API_KEY" in missing["error"]
