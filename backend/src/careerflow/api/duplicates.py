from collections.abc import Generator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerflow.application.jobs.dedup import DedupError, DedupService, DuplicateNotFoundError
from careerflow.infrastructure.database.models import (
    JobDuplicateModel,
    JobMergeModel,
    JobModel,
    JobSourceRecordModel,
)
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(tags=["duplicates"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


class JobBrief(BaseModel):
    id: str
    title: str
    company: str
    location_text: str | None
    remote_type: str | None
    salary_min: float | None
    salary_max: float | None
    posted_at: datetime | None
    source_count: int


class DuplicateOutput(BaseModel):
    id: str
    classification: str
    score: float
    reasons: list[str]
    status: str
    created_at: datetime
    job: JobBrief  # the newer posting
    canonical: JobBrief  # the older posting (kept by default)


class MergeOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    canonical_job_id: str
    merged_job_id: str
    source_record_ids: list[str]
    merged_at: datetime
    unmerged_at: datetime | None
    actor: str | None


class MergeRequest(BaseModel):
    keep_job_id: str | None = None  # default: the older posting
    actor: str | None = None


class DirectMergeRequest(BaseModel):
    canonical_job_id: str
    merged_job_id: str
    actor: str | None = None


def _brief(session: Session, job_id: str) -> JobBrief:
    job = session.get(JobModel, job_id)
    assert job is not None
    count = session.scalar(
        select(func.count()).select_from(JobSourceRecordModel).where(JobSourceRecordModel.job_id == job_id)
    )
    return JobBrief(
        id=job.id,
        title=job.title,
        company=job.company,
        location_text=job.location_text,
        remote_type=job.remote_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        posted_at=job.posted_at,
        source_count=int(count or 0),
    )


def _out(session: Session, row: JobDuplicateModel) -> DuplicateOutput:
    return DuplicateOutput(
        id=row.id,
        classification=row.classification,
        score=row.score,
        reasons=list(row.reasons or []),
        status=row.status,
        created_at=row.created_at,
        job=_brief(session, row.job_id),
        canonical=_brief(session, row.canonical_job_id),
    )


def _translate(error: DedupError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(error, DuplicateNotFoundError) else status.HTTP_409_CONFLICT
    return HTTPException(code, detail=str(error) or "not found")


@router.get("/duplicates", response_model=list[DuplicateOutput])
def list_duplicates(
    status_: Annotated[str | None, Query(alias="status")] = "PENDING",
    session: Session = Depends(get_session),
) -> list[DuplicateOutput]:
    """Suspected duplicate pairs for review (``?status=`` PENDING, MERGED, DISMISSED)."""
    return [_out(session, r) for r in DedupService(session).list_duplicates(status_)]


@router.post("/duplicates/{duplicate_id}/merge", response_model=MergeOutput)
def merge_duplicate(
    duplicate_id: str, payload: MergeRequest | None = None, session: Session = Depends(get_session)
) -> MergeOutput:
    payload = payload or MergeRequest()
    try:
        merge = DedupService(session).merge_duplicate(duplicate_id, payload.keep_job_id, payload.actor)
    except DedupError as error:
        raise _translate(error) from error
    return MergeOutput.model_validate(merge)


@router.post("/duplicates/{duplicate_id}/dismiss", response_model=DuplicateOutput)
def dismiss_duplicate(duplicate_id: str, session: Session = Depends(get_session)) -> DuplicateOutput:
    try:
        row = DedupService(session).dismiss(duplicate_id)
    except DedupError as error:
        raise _translate(error) from error
    return _out(session, row)


@router.post("/merges", response_model=MergeOutput, status_code=status.HTTP_201_CREATED)
def merge_jobs(payload: DirectMergeRequest, session: Session = Depends(get_session)) -> MergeOutput:
    """Merge two jobs the user knows are the same, without a detected suggestion."""
    try:
        merge = DedupService(session).merge_jobs(payload.canonical_job_id, payload.merged_job_id, payload.actor)
    except DedupError as error:
        raise _translate(error) from error
    return MergeOutput.model_validate(merge)


@router.get("/merges", response_model=list[MergeOutput])
def list_merges(active_only: bool = True, session: Session = Depends(get_session)) -> list[MergeOutput]:
    return [MergeOutput.model_validate(m) for m in DedupService(session).list_merges(active_only)]


@router.post("/merges/{merge_id}/unmerge", response_model=MergeOutput)
def unmerge(merge_id: str, session: Session = Depends(get_session)) -> MergeOutput:
    try:
        merge: JobMergeModel = DedupService(session).unmerge(merge_id)
    except DedupError as error:
        raise _translate(error) from error
    return MergeOutput.model_validate(merge)
