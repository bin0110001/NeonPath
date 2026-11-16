"""Build the configured LlmProvider. New providers register in PROVIDERS."""

from __future__ import annotations

from collections.abc import Callable

from careerflow.domain.ai.config import AiConfig
from careerflow.domain.ai.ports import LlmProvider
from careerflow.infrastructure.llm.http_providers import (
    AnthropicProvider,
    LlmHttp,
    OpenAICompatibleProvider,
)
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider

OLLAMA_ENDPOINT = "http://localhost:11434/v1"

# name -> factory(config, http). ``http`` is injected by tests; None = real network client.
ProviderFactory = Callable[[AiConfig, LlmHttp | None], LlmProvider]

PROVIDERS: dict[str, ProviderFactory] = {
    "fixture": lambda c, http: FixtureProvider(c.model or "fixture-1"),
    "openai_compatible": lambda c, http: OpenAICompatibleProvider(
        c.endpoint or "https://api.openai.com/v1", c.model, c.api_key, http
    ),
    "ollama": lambda c, http: OpenAICompatibleProvider(
        c.endpoint or OLLAMA_ENDPOINT, c.model, c.api_key, http, name="ollama"
    ),
    "anthropic": lambda c, http: AnthropicProvider(
        c.model or "claude-sonnet-5-5", c.api_key, c.endpoint or "https://api.anthropic.com", http
    ),
}

# What the UI needs to explain each provider (no secrets).
PROVIDER_INFO: dict[str, dict[str, object]] = {
    "fixture": {"label": "Fixture (offline demo)", "needs_key": False, "needs_endpoint": False},
    "openai_compatible": {"label": "OpenAI-compatible API", "needs_key": True, "needs_endpoint": True},
    "ollama": {"label": "Ollama (local)", "needs_key": False, "needs_endpoint": True},
    "anthropic": {"label": "Anthropic (hosted)", "needs_key": True, "needs_endpoint": False},
}


def build_provider(config: AiConfig, http: LlmHttp | None = None) -> LlmProvider:
    """AI disabled (the default) always yields DisabledProvider."""
    if not config.enabled:
        return DisabledProvider()
    try:
        factory = PROVIDERS[config.provider]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown AI provider {config.provider!r} (known: {known})") from None
    return factory(config, http)
