# How to write an LLM provider

A provider turns a prompt into text. Everything else (versioned prompts, JSON validation, one repair retry, timeouts and backoff, usage tracking, evidence checks) is done by the application layer, and domain code never imports a provider SDK ([ADR-007](../adr/ADR-007-llm-provider-abstraction.md), [ADR-012](../adr/ADR-012-versioned-prompts-and-evaluations.md)).

## 1. The contract

`backend/src/careerflow/domain/ai/ports.py`:

```python
class LlmProvider(Protocol):
    name: str
    model: str
    def complete(self, request: CompletionRequest) -> CompletionResult: ...
```

`CompletionRequest` has `system`, `user`, `json_output`, `timeout_seconds` and the prompt key/version (for logging). Return `CompletionResult(text, provider, model, usage=Usage(input_tokens, output_tokens))`; report token counts when the API gives them.

Raise only `AiError` subclasses, mapping failures like this:

| Situation | Raise |
|---|---|
| Request timed out | `AiTimeoutError` (retried with backoff) |
| HTTP 429 | `AiRateLimitError` (retried with backoff) |
| 401/403, other 4xx/5xx, unreadable response | `AiProviderError` (not retried) |
| AI not configured | `AiUnavailableError` (features report "unavailable") |

Never put the API key or response bodies in an error message: keys can be echoed back.

## 2. Example: an OpenAI-compatible-style provider over HTTP

Use the injectable `LlmHttp` so tests stay offline (see `infrastructure/llm/http_providers.py`, which implements `OpenAICompatibleProvider` and `AnthropicProvider`):

```python
class MyProvider:
    name = "myprovider"

    def __init__(self, endpoint: str, model: str, api_key: str, http: LlmHttp | None = None) -> None:
        self.model, self._url, self._key = model, endpoint.rstrip("/") + "/generate", api_key
        self._http = http or HttpxLlmClient()

    def complete(self, request: CompletionRequest) -> CompletionResult:
        response = self._http.post_json(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},     # headers only, never URLs
            body={"model": self.model, "system": request.system, "prompt": request.user},
            timeout=request.timeout_seconds,
        )
        data = _check(response, self.name)       # maps 429/401/5xx to the errors above
        return CompletionResult(data["text"], self.name, self.model)
```

## 3. Register it

In `infrastructure/llm/factory.py` add a factory to `PROVIDERS` and a label to `PROVIDER_INFO` (used by the settings page):

```python
PROVIDERS["myprovider"] = lambda c, http: MyProvider(c.endpoint, c.model, c.api_key, http)
PROVIDER_INFO["myprovider"] = {"label": "My provider", "needs_key": True, "needs_endpoint": True}
```

The key comes from the `AI_API_KEY` environment variable and is never stored or returned; users choose the provider, model and endpoint under *Settings* (or `AI_PROVIDER`, `AI_MODEL`, `AI_ENDPOINT` in `.env`) and can press *Test connection*.

## 4. Test it

Without any network or key: record sample responses and follow `tests/unit/ai/test_providers_and_config.py`, which checks request shape, usage, every failure mapping, that the key never appears in errors, and that the provider works through `AiClient` including the JSON repair retry. Domain/application code is also scanned in CI for provider SDK imports, so keep SDK usage inside `infrastructure/llm`.
