"""Duplicate review, merge and reversible unmerge.

Exact duplicates (same fingerprint) are attached to the existing job at ingestion time.
Probable duplicates are recorded for human review. A merge moves the duplicate's source
records onto the canonical job and hides the duplicate; unmerge restores both exactly.
Workflow state and history are never moved or rewritten: they stay on the job they
belong to, so unmerging brings every decision back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from careerflow.domain.jobs.dedup import DISTINCT, JobSignature, MatchResult, match
from careerflow.domain.jobs.fingerprint import normalize_company
from careerflow.infrastructure.database.models import (
    JobDuplicateModel,
    JobMergeModel,
    JobModel,
    JobSourceRecordModel,
)

PENDING, MERGED, DISMISSED = "PENDING", "MERGED", "DISMISSED"


class DedupError(Exception):
    pass


class DuplicateNotFoundError(DedupError):
    pass


def signature(job: JobModel) -> JobSignature:
    requisition = (job.raw_metadata_json or {}).get("requisition_id")
    return JobSignature(
        company=job.company,
        title=job.title,
        location=job.location_text,
        description=job.description_text,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        posted_at=job.posted_at,
        requisition_id=str(requisition) if requisition else None,
    )


class DedupService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- detection -----------------------------------------------------------------------

    def find_exact(self, company: str, fingerprint: str) -> JobModel | None:
        return self.session.scalars(
            select(JobModel)
            .where(JobModel.fingerprint == fingerprint, JobModel.merged_into_id.is_(None))
            .order_by(JobModel.discovered_at)
        ).first()

    def scan(self, job: JobModel) -> list[JobDuplicateModel]:
        """Record review candidates (LIKELY/POSSIBLE/EXACT) for ``job``; idempotent per pair."""
        wanted = normalize_company(job.company)
        first = wanted.split(" ")[0] if wanted else ""
        query = select(JobModel).where(JobModel.id != job.id, JobModel.merged_into_id.is_(None))
        if first:  # cheap pre-filter; match() does the exact company comparison
            query = query.where(JobModel.company.ilike(f"{first}%"))
        candidates = self.session.scalars(query)
        mine = signature(job)
        created: list[JobDuplicateModel] = []
        for other in candidates:
            result: MatchResult = match(mine, signature(other))
            if result.classification == DISTINCT or self._pair_exists(job.id, other.id):
                continue
            older, newer = sorted((job, other), key=lambda j: (j.discovered_at, j.id))
            row = JobDuplicateModel(
                job_id=newer.id,
                canonical_job_id=older.id,
                classification=result.classification,
                score=result.score,
                reasons=result.reasons,
            )
            self.session.add(row)
            created.append(row)
        self.session.commit()
        return created

    def _pair_exists(self, a: str, b: str) -> bool:
        return (
            self.session.scalars(
                select(JobDuplicateModel.id).where(
                    or_(
                        (JobDuplicateModel.job_id == a) & (JobDuplicateModel.canonical_job_id == b),
                        (JobDuplicateModel.job_id == b) & (JobDuplicateModel.canonical_job_id == a),
                    )
                )
            ).first()
            is not None
        )

    # -- review --------------------------------------------------------------------------

    def list_duplicates(self, status: str | None = PENDING) -> list[JobDuplicateModel]:
        statement = select(JobDuplicateModel).order_by(JobDuplicateModel.score.desc(), JobDuplicateModel.created_at)
        if status:
            statement = statement.where(JobDuplicateModel.status == status)
        return list(self.session.scalars(statement))

    def get(self, duplicate_id: str) -> JobDuplicateModel:
        row = self.session.get(JobDuplicateModel, duplicate_id)
        if row is None:
            raise DuplicateNotFoundError(duplicate_id)
        return row

    def dismiss(self, duplicate_id: str) -> JobDuplicateModel:
        row = self.get(duplicate_id)
        if row.status != PENDING:
            raise DedupError(f"duplicate is already {row.status}")
        row.status, row.resolved_at = DISMISSED, datetime.now(UTC)
        self.session.commit()
        return row

    def merge_duplicate(self, duplicate_id: str, keep_job_id: str | None = None, actor: str | None = None) -> JobMergeModel:
        """Merge a reviewed pair. By default the older posting is kept as canonical."""
        row = self.get(duplicate_id)
        if row.status != PENDING:
            raise DedupError(f"duplicate is already {row.status}")
        pair = {row.job_id, row.canonical_job_id}
        keep = keep_job_id or row.canonical_job_id
        if keep not in pair:
            raise DedupError("keep_job_id must be one of the two jobs in the pair")
        merged_id = (pair - {keep}).pop()
        merge = self.merge_jobs(keep, merged_id, actor)
        row.status, row.resolved_at = MERGED, datetime.now(UTC)
        self.session.commit()
        return merge

    # -- merge / unmerge ---------------------------------------------------------------------

    def merge_jobs(self, canonical_id: str, merged_id: str, actor: str | None = None) -> JobMergeModel:
        if canonical_id == merged_id:
            raise DedupError("cannot merge a job into itself")
        canonical, merged = self.session.get(JobModel, canonical_id), self.session.get(JobModel, merged_id)
        if canonical is None or merged is None:
            raise DedupError("job not found")
        if canonical.merged_into_id or merged.merged_into_id:
            raise DedupError("a job that is already merged cannot take part in another merge")
        children = self.session.scalars(select(JobModel.id).where(JobModel.merged_into_id == merged_id)).first()
        if children:
            raise DedupError("other jobs are merged into this one; unmerge them first")
        records = list(
            self.session.scalars(select(JobSourceRecordModel).where(JobSourceRecordModel.job_id == merged_id))
        )
        merge = JobMergeModel(
            canonical_job_id=canonical_id,
            merged_job_id=merged_id,
            source_record_ids=[r.id for r in records],
            actor=actor or "user",
        )
        for record in records:
            record.job_id = canonical_id
        merged.merged_into_id = canonical_id
        self.session.add(merge)
        self.session.commit()
        self.session.refresh(merge)
        return merge

    def unmerge(self, merge_id: str) -> JobMergeModel:
        merge = self.session.get(JobMergeModel, merge_id)
        if merge is None:
            raise DuplicateNotFoundError(merge_id)
        if merge.unmerged_at is not None:
            raise DedupError("this merge was already undone")
        merged = self.session.get(JobModel, merge.merged_job_id)
        if merged is None:
            raise DedupError("merged job no longer exists")
        for record in self.session.scalars(
            select(JobSourceRecordModel).where(JobSourceRecordModel.id.in_(merge.source_record_ids))
        ):
            record.job_id = merge.merged_job_id
        merged.merged_into_id = None
        merge.unmerged_at = datetime.now(UTC)
        for pair in self.session.scalars(
            select(JobDuplicateModel).where(
                JobDuplicateModel.status == MERGED,
                or_(
                    (JobDuplicateModel.job_id == merge.merged_job_id)
                    & (JobDuplicateModel.canonical_job_id == merge.canonical_job_id),
                    (JobDuplicateModel.job_id == merge.canonical_job_id)
                    & (JobDuplicateModel.canonical_job_id == merge.merged_job_id),
                ),
            )
        ):
            pair.status, pair.resolved_at = PENDING, None  # back in the review queue
        self.session.commit()
        return merge

    def merges_for(self, job_id: str) -> list[JobMergeModel]:
        return list(
            self.session.scalars(
                select(JobMergeModel)
                .where(or_(JobMergeModel.canonical_job_id == job_id, JobMergeModel.merged_job_id == job_id))
                .order_by(JobMergeModel.merged_at.desc())
            )
        )

    def list_merges(self, active_only: bool = True) -> list[JobMergeModel]:
        statement = select(JobMergeModel).order_by(JobMergeModel.merged_at.desc())
        if active_only:
            statement = statement.where(JobMergeModel.unmerged_at.is_(None))
        return list(self.session.scalars(statement))
