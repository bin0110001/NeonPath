"""Build the configured LlmProvider. New providers register in PROVIDERS."""

from __future__ import annotations

from collections.abc import Callable

from careerflow.domain.ai.ports import LlmProvider
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.settings import Settings

PROVIDERS: dict[str, Callable[[Settings], LlmProvider]] = {
    "fixture": lambda settings: FixtureProvider(settings.ai_model or "fixture-1"),
}


def build_provider(settings: Settings) -> LlmProvider:
    """AI_ENABLED=false (the default) always yields DisabledProvider."""
    if not settings.ai_enabled:
        return DisabledProvider()
    try:
        return PROVIDERS[settings.ai_provider](settings)
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown AI_PROVIDER {settings.ai_provider!r} (known: {known})") from None
