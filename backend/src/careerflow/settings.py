from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://careerflow:careerflow-dev-password@db:5432/careerflow"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    # Comma-separated literal values that must never appear in logs (e.g. API keys).
    log_redact_values: str = ""
    demo_mode: bool = False
    # AI is optional: with AI_ENABLED=false every non-AI workflow keeps working.
    raw_payload_retention_days: int = 90  # 0 keeps raw source payloads forever
    listing_stale_days: int = 14  # unseen this long (while its source works) -> EXPIRED
    worker_poll_seconds: float = 2.0
    worker_lease_seconds: float = 60.0
    ai_enabled: bool = False
    ai_provider: str = "fixture"
    ai_model: str = ""
    ai_endpoint: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: float = 30.0
    auth_mode: str = "local"

    @property
    def redact_value_list(self) -> list[str]:
        values = [v.strip() for v in self.log_redact_values.split(",") if v.strip()]
        return [*values, self.ai_api_key] if self.ai_api_key else values

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
