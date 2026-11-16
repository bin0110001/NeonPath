"""Network LLM providers: OpenAI-compatible (OpenAI, Ollama, vLLM, ...) and Anthropic.

Both talk JSON over HTTPS through an injectable ``LlmHttp`` so tests use recorded
responses and never touch the network. API keys are sent only as headers and are
never included in error messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from careerflow.domain.ai.ports import (
    AiProviderError,
    AiRateLimitError,
    AiTimeoutError,
    CompletionRequest,
    CompletionResult,
    Usage,
)

USER_AGENT = "CareerFlow/0.1"
ANTHROPIC_VERSION = "2023-06-01"


@dataclass(frozen=True)
class LlmHttpResponse:
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class LlmHttp(Protocol):
    def post_json(
        self, url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> LlmHttpResponse: ...


class HttpxLlmClient:
    def post_json(
        self, url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> LlmHttpResponse:
        try:
            response = httpx.post(
                url, headers={"User-Agent": USER_AGENT, **headers}, json=body, timeout=timeout
            )
        except httpx.TimeoutException as error:
            raise AiTimeoutError(f"provider did not answer within {timeout}s") from error
        except httpx.HTTPError as error:
            raise AiProviderError(f"could not reach the provider ({type(error).__name__})") from error
        return LlmHttpResponse(response.status_code, response.text, dict(response.headers))


def _check(response: LlmHttpResponse, provider: str) -> dict[str, Any]:
    """Map HTTP outcomes to AiError types; never echo response bodies (they may echo keys)."""
    if response.status == 429:
        raise AiRateLimitError(f"{provider} rate limit reached")
    if response.status in (401, 403):
        raise AiProviderError(f"{provider} rejected the credentials (HTTP {response.status})")
    if response.status >= 400:
        raise AiProviderError(f"{provider} returned HTTP {response.status}")
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise AiProviderError(f"{provider} returned a non-JSON response") from error
    if not isinstance(data, dict):
        raise AiProviderError(f"{provider} returned an unexpected response shape")
    return data


def _usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return usage if isinstance(usage, dict) else {}


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


class OpenAICompatibleProvider:
    """Chat Completions API: https://platform.openai.com/docs/api-reference/chat"""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str = "",
        http: LlmHttp | None = None,
        name: str = "openai_compatible",
    ) -> None:
        if not endpoint:
            raise ValueError("an endpoint is required (e.g. https://api.openai.com/v1 or http://localhost:11434/v1)")
        if not model:
            raise ValueError("a model name is required")
        self.name, self.model = name, model
        self._url = endpoint.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._http = http or HttpxLlmClient()

    def complete(self, request: CompletionRequest) -> CompletionResult:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if request.json_output:
            body["response_format"] = {"type": "json_object"}
        data = _check(
            self._http.post_json(self._url, headers=headers, body=body, timeout=request.timeout_seconds),
            self.name,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise AiProviderError(f"{self.name} response had no completion text") from error
        if not isinstance(text, str):
            raise AiProviderError(f"{self.name} response had no completion text")
        usage = _usage(data)
        return CompletionResult(
            text=text,
            provider=self.name,
            model=str(data.get("model") or self.model),
            usage=Usage(_int(usage.get("prompt_tokens")), _int(usage.get("completion_tokens"))),
        )


class AnthropicProvider:
    """Messages API: https://docs.anthropic.com/en/api/messages"""

    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str = "https://api.anthropic.com",
        http: LlmHttp | None = None,
        max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ValueError("AI_API_KEY is required for the anthropic provider")
        if not model:
            raise ValueError("a model name is required")
        self.model = model
        self._url = endpoint.rstrip("/") + "/v1/messages"
        self._key = api_key
        self._max_tokens = max_tokens
        self._http = http or HttpxLlmClient()

    def complete(self, request: CompletionRequest) -> CompletionResult:
        headers = {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION}
        body = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        data = _check(
            self._http.post_json(self._url, headers=headers, body=body, timeout=request.timeout_seconds),
            self.name,
        )
        blocks = data.get("content")
        text = "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ) if isinstance(blocks, list) else ""
        if not text:
            raise AiProviderError("anthropic response had no text content")
        usage = _usage(data)
        return CompletionResult(
            text=text,
            provider=self.name,
            model=str(data.get("model") or self.model),
            usage=Usage(_int(usage.get("input_tokens")), _int(usage.get("output_tokens"))),
        )
