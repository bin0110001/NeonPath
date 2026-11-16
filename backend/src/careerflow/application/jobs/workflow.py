"""Profile-scoped job workflow use cases (plan section 8)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileNotFoundError
from careerflow.domain.jobs.workflow import (
    INITIAL_STATUS,
    WorkflowStatus,
    validate_transition,
)
from careerflow.infrastructure.database.models import (
    JobModel,
    JobStatusHistoryModel,
    ProfileJobModel,
    ProfileModel,
)


class JobWorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _require(self, profile_id: str, job_id: str) -> None:
        if self.session.get(ProfileModel, profile_id) is None:
            raise ProfileNotFoundError(profile_id)
        if self.session.get(JobModel, job_id) is None:
            raise JobNotFoundError(job_id)

    def get_status(self, profile_id: str, job_id: str) -> WorkflowStatus:
        self._require(profile_id, job_id)
        row = self.session.get(ProfileJobModel, (profile_id, job_id))
        return WorkflowStatus(row.status) if row else INITIAL_STATUS

    def transition(
        self,
        profile_id: str,
        job_id: str,
        new_status: WorkflowStatus,
        actor: str | None = None,
        reason: str | None = None,
    ) -> WorkflowStatus:
        """Apply one validated transition and append exactly one history row.

        Raises InvalidTransitionError (nothing written) if the transition is not allowed.
        """
        old = self.get_status(profile_id, job_id)
        validate_transition(old, new_status)
        row = self.session.get(ProfileJobModel, (profile_id, job_id))
        if row is None:
            row = ProfileJobModel(profile_id=profile_id, job_id=job_id, status=new_status.value)
            self.session.add(row)
        else:
            row.status = new_status.value
        self.session.add(
            JobStatusHistoryModel(
                job_id=job_id,
                profile_id=profile_id,
                old_status=old.value,
                new_status=new_status.value,
                actor=actor or "user",
                reason=reason,
            )
        )
        self.session.commit()
        return new_status

    def history(self, profile_id: str, job_id: str) -> list[JobStatusHistoryModel]:
        self._require(profile_id, job_id)
        statement = (
            select(JobStatusHistoryModel)
            .where(
                JobStatusHistoryModel.profile_id == profile_id,
                JobStatusHistoryModel.job_id == job_id,
            )
            .order_by(JobStatusHistoryModel.timestamp, JobStatusHistoryModel.id)
        )
        return list(self.session.scalars(statement))
