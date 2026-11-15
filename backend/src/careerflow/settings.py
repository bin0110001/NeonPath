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
    auth_mode: str = "local"

    @property
    def redact_value_list(self) -> list[str]:
        return [v.strip() for v in self.log_redact_values.split(",") if v.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
