from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.profiles.service import ProfileNotFoundError
from careerflow.application.searches import (
    SearchConfigError,
    SearchNotFoundError,
    SearchService,
    schedule_key,
)
from careerflow.infrastructure.database.models import (
    ScheduledTaskModel,
    SearchDefinitionModel,
    SearchRunModel,
)
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(prefix="/profiles/{profile_id}/searches", tags=["searches"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


class SearchFilters(BaseModel):
    keywords_any: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    remote_type: str | None = None


class SearchInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_id: str
    query: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    schedule_minutes: int | None = Field(default=None, ge=5, le=60 * 24 * 30)
    max_results: int = Field(default=100, ge=1, le=500)
    enabled: bool = True


class SearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_id: str | None = None
    query: str | None = None
    location: str | None = None
    filters: SearchFilters | None = None
    schedule_minutes: int | None = Field(default=None, ge=5, le=60 * 24 * 30)
    max_results: int | None = Field(default=None, ge=1, le=500)
    enabled: bool | None = None


class SearchOutput(BaseModel):
    id: str
    profile_id: str
    source_id: str
    name: str
    enabled: bool
    query: str | None
    location: str | None
    filters: dict[str, Any]
    schedule_minutes: int | None
    max_results: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_schedule_status: str | None


class SearchRunOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    search_id: str
    source_run_id: str | None
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    discovered: int
    created: int
    updated: int
    skipped: int
    failed: int
    error_code: str | None
    error_message: str | None


def _out(session: Session, row: SearchDefinitionModel) -> SearchOutput:
    schedule = session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.key == schedule_key(row.id))).first()
    return SearchOutput(
        id=row.id, profile_id=row.profile_id, source_id=row.source_id, name=row.name, enabled=row.enabled,
        query=row.query, location=row.location, filters=row.filters_json, schedule_minutes=row.schedule_minutes,
        max_results=row.max_results, last_run_at=row.last_run_at,
        next_run_at=schedule.next_run_at if schedule and schedule.enabled else None,
        last_schedule_status=schedule.last_status if schedule else None,
    )  # fmt: skip


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if isinstance(error, SearchNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="search not found")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@router.get("", response_model=list[SearchOutput])
def list_searches(profile_id: str, session: Session = Depends(get_session)) -> list[SearchOutput]:
    try:
        return [_out(session, r) for r in SearchService(session).list_for_profile(profile_id)]
    except ProfileNotFoundError as error:
        raise _translate(error) from error


@router.post("", response_model=SearchOutput, status_code=status.HTTP_201_CREATED)
def create_search(profile_id: str, payload: SearchInput, session: Session = Depends(get_session)) -> SearchOutput:
    values = payload.model_dump(exclude={"filters"})
    values["filters_json"] = payload.filters.model_dump()
    try:
        return _out(session, SearchService(session).create(profile_id, values))
    except (ProfileNotFoundError, SearchConfigError) as error:
        raise _translate(error) from error


@router.patch("/{search_id}", response_model=SearchOutput)
def update_search(
    profile_id: str, search_id: str, payload: SearchUpdate, session: Session = Depends(get_session)
) -> SearchOutput:
    values = payload.model_dump(exclude_unset=True, exclude={"filters"})
    if payload.filters is not None:
        values["filters_json"] = payload.filters.model_dump()
    try:
        return _out(session, SearchService(session).update(profile_id, search_id, values))
    except (ProfileNotFoundError, SearchNotFoundError, SearchConfigError) as error:
        raise _translate(error) from error


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(profile_id: str, search_id: str, session: Session = Depends(get_session)) -> None:
    try:
        SearchService(session).delete(profile_id, search_id)
    except SearchNotFoundError as error:
        raise _translate(error) from error


@router.post("/{search_id}/run", response_model=SearchRunOutput)
def run_now(profile_id: str, search_id: str, session: Session = Depends(get_session)) -> SearchRunOutput:
    """Run Now: executes immediately; the outcome (counts and any source error) is in the run."""
    service = SearchService(session)
    try:
        search = service.get(profile_id, search_id)
    except SearchNotFoundError as error:
        raise _translate(error) from error
    if not search.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="search is disabled")
    return SearchRunOutput.model_validate(service.run(search_id, "manual"))


@router.get("/{search_id}/runs", response_model=list[SearchRunOutput])
def list_runs(
    profile_id: str,
    search_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[SearchRunOutput]:
    try:
        rows: list[SearchRunModel] = SearchService(session).runs(profile_id, search_id, limit)
    except SearchNotFoundError as error:
        raise _translate(error) from error
    return [SearchRunOutput.model_validate(r) for r in rows]

