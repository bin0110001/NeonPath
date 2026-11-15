"""Background maintenance (plan section 18): expiration, re-evaluation, retention pruning.

Nothing here deletes a job or its description: listings disappear from sources, but the
text a user evaluated against must survive (plan section 1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.infrastructure.database.models import (
    JobEvaluationModel,
    JobModel,
    JobSourceModel,
    JobSourceRecordModel,
    SourceRunModel,
    TaskModel,
)
from careerflow.infrastructure.tasks.queue import QUEUED, TaskQueue

ACTIVE, EXPIRED = "ACTIVE", "EXPIRED"
PRUNED_MARKER = "_pruned"
REEVALUATE_TASK = "reevaluate_profile"
RECENT_RUN_DAYS = 3  # a source must have run successfully this recently to trust "not seen"


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass
class ExpirationReport:
    expired: int = 0
    revived: int = 0


class MaintenanceService:
    def __init__(self, session: Session, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.session = session
        self.clock = clock

    # -- expiration -------------------------------------------------------------------------

    def check_expiration(self, stale_days: int = 14) -> ExpirationReport:
        """Mark listings EXPIRED when the posting says so or no source has seen it for
        ``stale_days`` while that source kind is demonstrably working; revive them if seen again."""
        now = self.clock()
        report = ExpirationReport()
        stale_before = now - timedelta(days=stale_days)
        healthy = self._healthy_adapters(now)
        jobs = self.session.scalars(select(JobModel).where(JobModel.merged_into_id.is_(None)))
        for job in jobs:
            records = list(self.session.scalars(select(JobSourceRecordModel).where(JobSourceRecordModel.job_id == job.id)))
            status = job.source_status or ACTIVE
            posting_expired = job.expires_at is not None and _utc(job.expires_at) <= now
            last_seen = max((_utc(r.last_seen_at) for r in records), default=None)
            vanished = (
                bool(records)
                and last_seen is not None
                and last_seen < stale_before
                and all(r.adapter in healthy for r in records)  # not just an outage
            )
            if status == ACTIVE and (posting_expired or vanished):
                job.source_status = EXPIRED
                report.expired += 1
            elif status == EXPIRED and not posting_expired and last_seen is not None and last_seen >= stale_before:
                job.source_status = ACTIVE
                report.revived += 1
        self.session.commit()
        return report

    def _healthy_adapters(self, now: datetime) -> set[str]:
        since = now - timedelta(days=RECENT_RUN_DAYS)
        rows = self.session.execute(
            select(JobSourceModel.adapter)
            .join(SourceRunModel, SourceRunModel.source_id == JobSourceModel.id)
            .where(SourceRunModel.status == "SUCCEEDED", SourceRunModel.finished_at >= since)
            .distinct()
        )
        # adapters with no recent successful run (or never run, e.g. manual pastes) never expire by absence
        return {row[0] for row in rows}

    # -- re-evaluation ----------------------------------------------------------------------

    def request_reevaluation(self, profile_id: str) -> TaskModel | None:
        """Queue one re-evaluation for the profile; coalesces if one is already waiting."""
        waiting = self.session.scalars(
            select(TaskModel).where(
                TaskModel.task_type == REEVALUATE_TASK,
                TaskModel.profile_id == profile_id,
                TaskModel.status == QUEUED,
            )
        ).first()
        if waiting is not None:
            return None
        return TaskQueue(self.session).enqueue(REEVALUATE_TASK, {"profile_id": profile_id}, profile_id=profile_id)

    def reevaluate_profile(self, profile_id: str) -> int:
        """Append a fresh evaluation for each job this profile already has one for.
        Other profiles' evaluations are untouched."""
        job_ids = list(
            self.session.scalars(
                select(JobEvaluationModel.job_id)
                .join(JobModel, JobModel.id == JobEvaluationModel.job_id)
                .where(JobEvaluationModel.profile_id == profile_id, JobModel.merged_into_id.is_(None))
                .distinct()
            )
        )
        service = EvaluationService(JobService(self.session), ProfileService(self.session))
        for job_id in job_ids:
            service.evaluate_job_for_profile(job_id, profile_id)
        return len(job_ids)

    # -- retention --------------------------------------------------------------------------

    def prune_raw_payloads(self, retention_days: int) -> int:
        """Replace raw source payloads older than the retention window with a marker.
        ``retention_days <= 0`` keeps everything. The canonical job text is never touched."""
        if retention_days <= 0:
            return 0
        cutoff = self.clock() - timedelta(days=retention_days)
        pruned = 0
        records = self.session.scalars(
            select(JobSourceRecordModel).where(JobSourceRecordModel.last_seen_at < cutoff)
        )
        for record in records:
            if record.raw_payload.get(PRUNED_MARKER):
                continue
            record.raw_payload = {PRUNED_MARKER: True, "pruned_at": self.clock().isoformat()}
            pruned += 1
        self.session.commit()
        return pruned
