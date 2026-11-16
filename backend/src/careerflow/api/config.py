from fastapi import APIRouter
from pydantic import BaseModel

from careerflow.demo import external_writes_allowed
from careerflow.settings import get_settings

router = APIRouter(prefix="/config", tags=["config"])


class AppConfig(BaseModel):
    demo_mode: bool
    auth_mode: str
    external_writes_enabled: bool


@router.get("", response_model=AppConfig)
def get_config() -> AppConfig:
    """Non-secret runtime flags the UI needs (e.g. to show the demo banner)."""
    settings = get_settings()
    return AppConfig(
        demo_mode=settings.demo_mode,
        auth_mode=settings.auth_mode,
        external_writes_enabled=external_writes_allowed(settings),
    )
