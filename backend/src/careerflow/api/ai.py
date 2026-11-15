from fastapi import APIRouter
from pydantic import BaseModel

from careerflow.infrastructure.llm.factory import build_provider
from careerflow.settings import get_settings

router = APIRouter(prefix="/ai", tags=["ai"])


class AiStatus(BaseModel):
    enabled: bool
    provider: str
    model: str
    available: bool


@router.get("/status", response_model=AiStatus)
def ai_status() -> AiStatus:
    """Whether AI features can be used. Never fails: disabled AI is a normal state."""
    settings = get_settings()
    try:
        provider = build_provider(settings)
    except ValueError:
        return AiStatus(enabled=settings.ai_enabled, provider=settings.ai_provider, model="", available=False)
    return AiStatus(
        enabled=settings.ai_enabled,
        provider=provider.name,
        model=provider.model,
        available=settings.ai_enabled,
    )
