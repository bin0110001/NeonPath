from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.application.sources.ingest import IngestionService
from careerflow.domain.sources.ports import DiscoveryRequest, SourceError
from careerflow.infrastructure.database.models import JobModel, JobSourceModel, SourceRunModel
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.infrastructure.jobsources.registry import (
    ADAPTERS,
    SECRET_KEYS,
    build_adapter,
    mask_config,
)

router = APIRouter(prefix="/sources", tags=["sources"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def _reject_inline_secrets(config: dict[str, Any]) -> dict[str, Any]:
    for key, value in config.items():
        lowered = key.lower()
        if any(s in lowered for s in SECRET_KEYS) and not lowered.endswith("_env") and value:
            raise ValueError(f"do not store secrets in config; use '{key}_env' naming an environment variable")
    return config


class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    adapter: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("config")
    @classmethod
    def _no_secrets(cls, config: dict[str, Any]) -> dict[str, Any]:
        return _reject_inline_secrets(config)


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("config")
    @classmethod
    def _no_secrets(cls, config: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if config is None else _reject_inline_secrets(config)


class SourceOutput(BaseModel):
    id: str
    name: str
    adapter: str
    config: dict[str, Any]
    enabled: bool
    health: str
    consecutive_failures: int
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime


class RunOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    discovered: int
    created: int
    updated: int
    failed: int
    error_code: str | None
    error_message: str | None


class RunRequest(BaseModel):
    query: str | None = None
    location: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


def _out(source: JobSourceModel) -> SourceOutput:
    return SourceOutput(
        id=source.id,
        name=source.name,
        adapter=source.adapter,
        config=mask_config(source.config_json),
        enabled=source.enabled,
        health=source.health,
        consecutive_failures=source.consecutive_failures,
        last_run_at=source.last_run_at,
        last_status=source.last_status,
        last_error=source.last_error,
        created_at=source.created_at,
    )


def _get(session: Session, source_id: str) -> JobSourceModel:
    source = session.get(JobSourceModel, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    return source


def _validate(adapter: str, config: dict[str, Any]) -> None:
    try:
        build_adapter(adapter, config)
    except SourceError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.get("/adapters", response_model=list[str])
def list_adapters() -> list[str]:
    return sorted(ADAPTERS)


@router.get("", response_model=list[SourceOutput])
def list_sources(session: Session = Depends(get_session)) -> list[SourceOutput]:
    return [_out(s) for s in session.scalars(select(JobSourceModel).order_by(JobSourceModel.name))]


@router.post("", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceInput, session: Session = Depends(get_session)) -> SourceOutput:
    _validate(payload.adapter, payload.config)
    source = JobSourceModel(
        name=payload.name, adapter=payload.adapter, config_json=payload.config, enabled=payload.enabled
    )
    session.add(source)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="a source with that name exists") from error
    return _out(source)


@router.patch("/{source_id}", response_model=SourceOutput)
def update_source(
    source_id: str, payload: SourceUpdate, session: Session = Depends(get_session)
) -> SourceOutput:
    source = _get(session, source_id)
    if payload.config is not None:
        _validate(source.adapter, payload.config)
        source.config_json = payload.config
    if payload.name is not None:
        source.name = payload.name
    if payload.enabled is not None:
        source.enabled = payload.enabled
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="a source with that name exists") from error
    return _out(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: str, session: Session = Depends(get_session)) -> None:
    source = _get(session, source_id)
    for run in session.scalars(select(SourceRunModel).where(SourceRunModel.source_id == source_id)):
        session.delete(run)
    session.delete(source)
    session.commit()


@router.post("/{source_id}/run", response_model=RunOutput)
def run_now(
    source_id: str, payload: RunRequest | None = None, session: Session = Depends(get_session)
) -> RunOutput:
    """Run the source immediately ("Run now"). The outcome, including failures, is in the run."""
    source = _get(session, source_id)
    if not source.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="source is disabled")
    evaluation = EvaluationService(JobService(session), ProfileService(session))

    def evaluate_new(job: JobModel) -> None:
        evaluation.evaluate_job_for_all_profiles(job.id)

    request = DiscoveryRequest(**(payload.model_dump() if payload else {}))
    run = IngestionService(session, on_created=evaluate_new).run_source(source_id, "manual", request)
    return RunOutput.model_validate(run)


@router.get("/{source_id}/runs", response_model=list[RunOutput])
def list_runs(
    source_id: str, limit: int = Query(default=20, ge=1, le=200), session: Session = Depends(get_session)
) -> list[RunOutput]:
    _get(session, source_id)
    statement = (
        select(SourceRunModel)
        .where(SourceRunModel.source_id == source_id)
        .order_by(SourceRunModel.started_at.desc())
        .limit(limit)
    )
    return [RunOutput.model_validate(r) for r in session.scalars(statement)]
