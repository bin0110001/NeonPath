import time
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.application.ai.config import SINGLETON_ID, effective_config
from careerflow.domain.ai.config import AiConfig
from careerflow.domain.ai.ports import AiError, CompletionRequest
from careerflow.infrastructure.database.models import AiConfigModel
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.infrastructure.llm.factory import PROVIDER_INFO, PROVIDERS, build_provider
from careerflow.infrastructure.llm.http_providers import LlmHttp

router = APIRouter(prefix="/ai", tags=["ai"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def get_llm_http() -> LlmHttp | None:
    """Overridden in tests so connectivity checks never touch the network."""
    return None


class AiStatus(BaseModel):
    enabled: bool
    provider: str
    model: str
    available: bool


class AiConfigOutput(BaseModel):
    enabled: bool
    provider: str
    model: str
    endpoint: str
    api_key_set: bool  # only whether a key exists, never the key
    source: str
    timeout_seconds: float
    providers: dict[str, dict[str, object]]


class AiConfigInput(BaseModel):
    """Non-secret selection. The API key is set with the AI_API_KEY environment variable."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str
    model: str = Field(default="", max_length=200)
    endpoint: str = Field(default="", max_length=500)


class TestResult(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: float | None = None
    error: str | None = None


def _config_out(config: AiConfig) -> AiConfigOutput:
    return AiConfigOutput(
        enabled=config.enabled,
        provider=config.provider,
        model=config.model,
        endpoint=config.endpoint,
        api_key_set=bool(config.api_key),
        source=config.source,
        timeout_seconds=config.timeout_seconds,
        providers=PROVIDER_INFO,
    )


@router.get("/status", response_model=AiStatus)
def ai_status(session: Session = Depends(get_session)) -> AiStatus:
    """Whether AI features can be used. Never fails: disabled AI is a normal state."""
    config = effective_config(session)
    try:
        provider = build_provider(config)
    except ValueError:
        return AiStatus(enabled=config.enabled, provider=config.provider, model="", available=False)
    return AiStatus(enabled=config.enabled, provider=provider.name, model=provider.model, available=config.enabled)


@router.get("/config", response_model=AiConfigOutput)
def get_config(session: Session = Depends(get_session)) -> AiConfigOutput:
    return _config_out(effective_config(session))


@router.put("/config", response_model=AiConfigOutput)
def put_config(payload: AiConfigInput, session: Session = Depends(get_session)) -> AiConfigOutput:
    if payload.provider not in PROVIDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown provider; known: {sorted(PROVIDERS)}")
    row = session.get(AiConfigModel, SINGLETON_ID)
    if row is None:
        row = AiConfigModel(id=SINGLETON_ID)
        session.add(row)
    row.enabled, row.provider = payload.enabled, payload.provider
    row.model, row.endpoint = payload.model.strip(), payload.endpoint.strip()
    session.commit()
    return _config_out(effective_config(session))


@router.delete("/config", response_model=AiConfigOutput)
def reset_config(session: Session = Depends(get_session)) -> AiConfigOutput:
    """Forget the saved selection and fall back to the environment defaults."""
    row = session.get(AiConfigModel, SINGLETON_ID)
    if row is not None:
        session.delete(row)
        session.commit()
    return _config_out(effective_config(session))


@router.post("/test", response_model=TestResult)
def test_connection(
    session: Session = Depends(get_session), http: LlmHttp | None = Depends(get_llm_http)
) -> TestResult:
    """Send a tiny request through the configured provider and report success or a readable error."""
    config = effective_config(session)
    if not config.enabled:
        return TestResult(ok=False, provider="disabled", model="none", error="AI is disabled")
    try:
        provider = build_provider(config, http)
    except ValueError as error:  # bad provider name, missing model/endpoint/key
        return TestResult(ok=False, provider=config.provider, model=config.model, error=str(error))
    request = CompletionRequest(
        system="Reply with the single word: pong", user="ping", prompt_key="connectivity_test",
        prompt_version="v1", json_output=False, timeout_seconds=min(config.timeout_seconds, 20.0),
    )  # fmt: skip
    started = time.perf_counter()
    try:
        result = provider.complete(request)
    except AiError as error:
        return TestResult(ok=False, provider=provider.name, model=provider.model, error=str(error))
    latency = round((time.perf_counter() - started) * 1000, 1)
    return TestResult(ok=bool(result.text.strip()), provider=result.provider, model=result.model, latency_ms=latency)
