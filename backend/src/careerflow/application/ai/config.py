"""Effective AI configuration: environment defaults overridden by the saved selection.

Secrets (``AI_API_KEY``) only ever come from the environment; the database stores just
the non-secret choice (enabled/provider/model/endpoint).
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from careerflow.application.ai.client import AiClient, RetryPolicy
from careerflow.domain.ai.config import AiConfig
from careerflow.domain.ai.ports import LlmProvider
from careerflow.infrastructure.database.models import AiConfigModel
from careerflow.infrastructure.llm.factory import build_provider
from careerflow.infrastructure.llm.http_providers import LlmHttp
from careerflow.settings import Settings, get_settings

SINGLETON_ID = "default"


def effective_config(session: Session | None, settings: Settings | None = None) -> AiConfig:
    settings = settings or get_settings()
    config = AiConfig(
        enabled=settings.ai_enabled,
        provider=settings.ai_provider,
        model=settings.ai_model,
        endpoint=settings.ai_endpoint,
        api_key=settings.ai_api_key,
        timeout_seconds=settings.ai_timeout_seconds,
        source="environment",
    )
    row = session.get(AiConfigModel, SINGLETON_ID) if session is not None else None
    if row is None:
        return config
    return replace(
        config, enabled=row.enabled, provider=row.provider, model=row.model, endpoint=row.endpoint, source="saved"
    )


def build_client(
    session: Session | None, settings: Settings | None = None, http: LlmHttp | None = None
) -> AiClient:
    config = effective_config(session, settings)
    return AiClient(build_provider(config, http), retry=RetryPolicy(timeout_seconds=config.timeout_seconds))


def provider_for(session: Session | None, http: LlmHttp | None = None) -> LlmProvider:
    return build_provider(effective_config(session), http)
