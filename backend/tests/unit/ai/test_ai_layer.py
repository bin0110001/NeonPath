import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

import careerflow
from careerflow.application.ai.client import AiClient, RetryPolicy
from careerflow.application.ai.prompts import PromptNotFoundError, PromptRegistry
from careerflow.domain.ai.ports import (
    AiInvalidResponseError,
    AiProviderError,
    AiRateLimitError,
    AiTimeoutError,
    AiUnavailableError,
    CompletionRequest,
    LlmProvider,
)
from careerflow.infrastructure.llm.factory import build_provider
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.main import create_app
from careerflow.settings import Settings, get_settings


class Echo(BaseModel):
    echoed: str
    count: int = 1


def request(key: str = "echo_test") -> CompletionRequest:
    return CompletionRequest(system="s", user="u", prompt_key=key, prompt_version="v1", timeout_seconds=5)


def client(provider: LlmProvider, **retry: float) -> tuple[AiClient, list[float]]:
    sleeps: list[float] = []
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=1.0, **retry)  # type: ignore[arg-type]
    return AiClient(provider, retry=policy, sleep=sleeps.append), sleeps


# --- contract every *enabled* provider must satisfy ------------------------------------------


def fixture_provider() -> LlmProvider:
    return FixtureProvider().script("echo_test", '{"echoed": "hi"}')


ENABLED_PROVIDERS = [fixture_provider]


@pytest.mark.parametrize("make", ENABLED_PROVIDERS)
def test_provider_contract_returns_text_and_provenance(make: object) -> None:
    provider: LlmProvider = make()  # type: ignore[operator]
    assert provider.name and provider.model
    result = provider.complete(request())
    assert isinstance(result.text, str) and result.text
    assert (result.provider, result.model) == (provider.name, provider.model)
    assert result.usage.input_tokens is None or result.usage.input_tokens >= 0


@pytest.mark.parametrize("make", ENABLED_PROVIDERS)
def test_provider_contract_only_raises_ai_errors(make: object) -> None:
    from careerflow.domain.ai.ports import AiError

    provider: LlmProvider = make()  # type: ignore[operator]
    try:
        provider.complete(request("unscripted_key"))
    except AiError:
        pass  # any AiError subclass is acceptable; anything else would propagate and fail


def test_disabled_provider_reports_unavailable() -> None:
    with pytest.raises(AiUnavailableError):
        DisabledProvider().complete(request())


# --- structured client -----------------------------------------------------------------------


def test_valid_output_returns_provenance() -> None:
    provider = FixtureProvider("m-1").script("echo_test", '{"echoed": "hello", "count": 2}')
    ai, _ = client(provider)
    result = ai.run("echo_test", {"text": "hello"}, Echo)
    assert result.value == Echo(echoed="hello", count=2)
    assert (result.provider, result.model) == ("fixture", "m-1")
    assert (result.prompt_key, result.prompt_version) == ("echo_test", "v2")  # newest wins
    assert result.attempts == 1
    assert result.usage.input_tokens and result.usage.output_tokens
    sent = provider.calls[0].request
    assert "hello" in sent.user and "echoed" in sent.user  # variables + schema rendered


def test_pinned_version_is_used() -> None:
    provider = FixtureProvider().script("echo_test", '{"echoed": "x"}')
    result = client(provider)[0].run("echo_test", {"text": "x"}, Echo, version="v1")
    assert result.prompt_version == "v1"
    assert "Text: x" in provider.calls[0].request.user


def test_markdown_fenced_json_is_accepted() -> None:
    provider = FixtureProvider().script("echo_test", '```json\n{"echoed": "x"}\n```')
    assert client(provider)[0].run("echo_test", {"text": "x"}, Echo).value.echoed == "x"


def test_invalid_output_gets_one_repair_attempt() -> None:
    provider = FixtureProvider().script("echo_test", "not json", '{"echoed": "fixed"}')
    result = client(provider)[0].run("echo_test", {"text": "x"}, Echo)
    assert result.value.echoed == "fixed"
    assert result.attempts == 2
    assert "not valid" in provider.calls[1].request.user


def test_still_invalid_after_repair_fails_and_keeps_metadata() -> None:
    provider = FixtureProvider().script("echo_test", '{"wrong": 1}', '{"count": "many"}')
    with pytest.raises(AiInvalidResponseError) as info:
        client(provider)[0].run("echo_test", {"text": "x"}, Echo)
    assert len(provider.calls) == 2  # exactly one repair, no more
    assert info.value.raw_text == '{"count": "many"}'
    assert len(info.value.validation_errors) == 2
    assert any("echoed" in e for e in info.value.validation_errors)


def test_timeout_and_rate_limit_are_retried_with_backoff() -> None:
    provider = FixtureProvider().script(
        "echo_test", AiTimeoutError("slow"), AiRateLimitError("429"), '{"echoed": "ok"}'
    )
    ai, sleeps = client(provider)
    result = ai.run("echo_test", {"text": "x"}, Echo)
    assert result.value.echoed == "ok"
    assert result.attempts == 3
    assert sleeps == [1.0, 2.0]


def test_retries_are_bounded() -> None:
    provider = FixtureProvider().script("echo_test", AiTimeoutError("slow"))
    ai, sleeps = client(provider)
    with pytest.raises(AiTimeoutError):
        ai.run("echo_test", {"text": "x"}, Echo)
    assert len(provider.calls) == 3
    assert len(sleeps) == 2


@pytest.mark.parametrize("error", [AiProviderError("boom"), AiUnavailableError("off")])
def test_other_errors_are_not_retried(error: Exception) -> None:
    provider = FixtureProvider().script("echo_test", error)  # type: ignore[arg-type]
    with pytest.raises(type(error)):
        client(provider)[0].run("echo_test", {"text": "x"}, Echo)
    assert len(provider.calls) == 1


def test_missing_prompt_variable_is_an_error_not_a_blank() -> None:
    provider = FixtureProvider().script("echo_test", '{"echoed": "x"}')
    with pytest.raises(KeyError):
        client(provider)[0].run("echo_test", {}, Echo)
    assert provider.calls == []


def test_timeout_policy_is_passed_to_the_provider() -> None:
    provider = FixtureProvider().script("echo_test", '{"echoed": "x"}')
    ai = AiClient(provider, retry=RetryPolicy(timeout_seconds=7.5))
    ai.run("echo_test", {"text": "x"}, Echo)
    assert provider.calls[0].request.timeout_seconds == 7.5


def test_disabled_provider_through_the_client() -> None:
    with pytest.raises(AiUnavailableError):
        client(DisabledProvider())[0].run("echo_test", {"text": "x"}, Echo)


# --- prompt registry -------------------------------------------------------------------------


def test_prompt_registry() -> None:
    registry = PromptRegistry()
    assert registry.versions("echo_test") == [1, 2]
    assert registry.get("echo_test").version == "v2"
    assert registry.get("echo_test", "v1").variables == {"text", "schema"}
    for bad in ("nope", "../etc", "Echo"):
        with pytest.raises(PromptNotFoundError):
            registry.get(bad)
    with pytest.raises(PromptNotFoundError):
        registry.get("echo_test", "v9")


# --- configuration ---------------------------------------------------------------------------


def test_ai_is_disabled_by_default() -> None:
    assert Settings().ai_enabled is False
    assert isinstance(build_provider(Settings()), DisabledProvider)


def test_fixture_provider_when_enabled_and_unknown_provider_rejected() -> None:
    assert build_provider(Settings(ai_enabled=True, ai_provider="fixture")).name == "fixture"
    with pytest.raises(ValueError, match="unknown AI_PROVIDER"):
        build_provider(Settings(ai_enabled=True, ai_provider="skynet"))


def test_status_endpoint_reports_unavailable_not_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    try:
        body = TestClient(create_app()).get("/api/v1/ai/status").json()
        assert body == {"enabled": False, "provider": "disabled", "model": "none", "available": False}
        monkeypatch.setenv("AI_ENABLED", "true")
        get_settings.cache_clear()
        assert TestClient(create_app()).get("/api/v1/ai/status").json()["available"] is True
        monkeypatch.setenv("AI_PROVIDER", "skynet")
        get_settings.cache_clear()
        broken = TestClient(create_app()).get("/api/v1/ai/status")
        assert broken.status_code == 200 and broken.json()["available"] is False
    finally:
        get_settings.cache_clear()


def test_domain_and_application_import_no_llm_sdk() -> None:
    root = Path(careerflow.__file__).parent
    forbidden = {"openai", "anthropic", "ollama", "httpx", "requests", "google", "cohere"}
    for folder in ("domain", "application"):
        for path in (root / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                assert not {n.split(".")[0] for n in names} & forbidden, path
