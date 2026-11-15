# ADR-007: LLM provider abstraction

## Status

Accepted

## Context

AI must be optional and vendor-neutral: hosted and local (OpenAI-compatible) models, no paid calls in CI, and every non-AI workflow must keep working with AI off.

## Decision

`domain/ai/ports.py` defines `LlmProvider` (a single `complete(request) -> result`), the request/result/usage types and the error hierarchy (`AiUnavailableError`, `AiTimeoutError`, `AiRateLimitError`, `AiProviderError`, `AiInvalidResponseError`). Domain and application code import nothing from a provider SDK (enforced by a test). Implementations live in `infrastructure/llm`: `DisabledProvider` (the default; reports "unavailable"), `FixtureProvider` (scripted, for tests/demos), and later OpenAI-compatible and hosted providers registered in `factory.PROVIDERS`. `AiClient` adds timeouts, bounded retry with backoff for timeouts/rate limits, structured-output validation and usage capture. `AI_ENABLED=false` is the default.

The provider call is synchronous. FastAPI runs sync endpoints in a threadpool and the worker is process based, so async would add complexity without benefit; the port can gain an async twin if streaming is ever needed.

## Alternatives considered

A single giant `generate()` used everywhere (no typed tasks); an SDK-specific abstraction such as LangChain (leaks types, heavy dependency); async-only port.

## Consequences

Providers are swappable without touching domain code. Each task-specific service (requirement extraction, semantic evaluation, ...) is a thin class over `AiClient` with its own prompt and response model.
