"""Profile-scoped job inbox queries: filtering, sorting, pagination and dashboard counts.

Everything is evaluated in SQL (never in the client) and always for one profile: the
workflow status comes from ``profile_jobs`` (absent row = READY_FOR_REVIEW) and the score
from that profile's latest evaluation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from careerflow.application.profiles.service import ProfileNotFoundError
from careerflow.domain.jobs.workflow import INITIAL_STATUS, WorkflowStatus
from careerflow.infrastructure.database.models import (
    JobEvaluationModel,
    JobModel,
    JobSourceRecordModel,
    ProfileJobModel,
    ProfileModel,
)

HIGH_FIT_THRESHOLD = 0.7
NEW_JOB_DAYS = 7

SortKey = Literal["discovered_at", "posted_at", "score", "title", "company"]


@dataclass
class JobFilters:
    status: str | None = None
    min_score: float | None = None
    remote_type: str | None = None
    location: str | None = None
    company: str | None = None
    source: str | None = None
    posted_after: datetime | None = None
    has_blockers: bool | None = None
    search: str | None = None


@dataclass
class JobRow:
    job: JobModel
    workflow_status: str
    score: float | None
    has_blockers: bool | None


@dataclass
class Dashboard:
    total: int
    new_jobs: int
    needs_review: int
    high_fit: int
    shortlisted: int
    blocked: int
    unevaluated: int
    by_status: dict[str, int]


class JobQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _base(self, profile_id: str, f: JobFilters) -> Select[Any]:
        if self.session.get(ProfileModel, profile_id) is None:
            raise ProfileNotFoundError(profile_id)
        latest_eval_id = (
            select(JobEvaluationModel.id)
            .where(
                JobEvaluationModel.job_id == JobModel.id,
                JobEvaluationModel.profile_id == profile_id,
            )
            .order_by(JobEvaluationModel.created_at.desc(), JobEvaluationModel.id)
            .limit(1)
            .correlate(JobModel)
            .scalar_subquery()
        )
        status = func.coalesce(ProfileJobModel.status, INITIAL_STATUS.value)
        statement: Any = (
            select(JobModel, status, JobEvaluationModel.overall_score, JobEvaluationModel.blockers)
            .outerjoin(
                ProfileJobModel,
                and_(ProfileJobModel.job_id == JobModel.id, ProfileJobModel.profile_id == profile_id),
            )
            .outerjoin(JobEvaluationModel, JobEvaluationModel.id == latest_eval_id)
        )
        if f.status:
            statement = statement.where(status == f.status)
        if f.min_score is not None:
            statement = statement.where(JobEvaluationModel.overall_score >= f.min_score)
        if f.remote_type:
            statement = statement.where(JobModel.remote_type == f.remote_type)
        if f.location:
            statement = statement.where(JobModel.location_text.ilike(f"%{f.location}%"))
        if f.company:
            statement = statement.where(JobModel.company.ilike(f"%{f.company}%"))
        if f.search:
            like = f"%{f.search}%"
            statement = statement.where(
                or_(JobModel.title.ilike(like), JobModel.description_text.ilike(like))
            )
        if f.posted_after:
            statement = statement.where(JobModel.posted_at >= f.posted_after)
        if f.source:
            statement = statement.where(
                select(JobSourceRecordModel.id)
                .where(
                    JobSourceRecordModel.job_id == JobModel.id,
                    JobSourceRecordModel.adapter == f.source,
                )
                .exists()
            )
        return cast("Select[Any]", statement)

    def _filter_blockers(self, rows: list[JobRow], wanted: bool | None) -> list[JobRow]:
        if wanted is None:
            return rows
        return [r for r in rows if r.has_blockers is not None and r.has_blockers == wanted]

    def _rows(self, profile_id: str, f: JobFilters) -> list[JobRow]:
        result: list[Any] = list(self.session.execute(self._base(profile_id, f)).all())
        rows = [
            JobRow(job, str(status), score, None if blockers is None else bool(blockers))
            for job, status, score, blockers in result
        ]
        return self._filter_blockers(rows, f.has_blockers)

    def search(
        self,
        profile_id: str,
        filters: JobFilters,
        sort: SortKey = "discovered_at",
        descending: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobRow], int]:
        """Return one page of rows and the total number of matches."""
        rows = self._rows(profile_id, filters)

        def value(row: JobRow) -> Any:
            if sort == "score":
                return row.score
            return getattr(row.job, sort)

        present = [r for r in rows if value(r) is not None]
        missing = [r for r in rows if value(r) is None]  # rows with no value always sort last
        present.sort(key=value, reverse=descending)
        ordered = present + missing
        return ordered[offset : offset + limit], len(ordered)

    def dashboard(self, profile_id: str, filters: JobFilters | None = None) -> Dashboard:
        rows = self._rows(profile_id, filters or JobFilters())
        cutoff = datetime.now(UTC) - timedelta(days=NEW_JOB_DAYS)

        def is_new(row: JobRow) -> bool:
            discovered = row.job.discovered_at
            if discovered.tzinfo is None:
                discovered = discovered.replace(tzinfo=UTC)
            return discovered >= cutoff

        review = WorkflowStatus.READY_FOR_REVIEW.value
        counts = Counter(r.workflow_status for r in rows)
        return Dashboard(
            total=len(rows),
            new_jobs=sum(1 for r in rows if is_new(r) and r.workflow_status == review),
            needs_review=counts[review],
            high_fit=sum(
                1
                for r in rows
                if r.score is not None and r.score >= HIGH_FIT_THRESHOLD and not r.has_blockers
            ),
            shortlisted=counts[WorkflowStatus.SHORTLISTED.value],
            blocked=sum(1 for r in rows if r.has_blockers),
            unevaluated=sum(1 for r in rows if r.score is None),
            by_status=dict(counts),
        )
