from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import (
    JobModel,
    JobEvaluationModel,
    JobRequirementModel,
    JobSourceRecordModel,
    JobStatusHistoryModel,
)

T = TypeVar("T")


class JobService:
    """Job use cases; HTTP and ORM serialization remain outside this layer."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_job(self, job_id: str) -> JobModel:
        job = self.session.get(JobModel, job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list_jobs(self) -> list[JobModel]:
        return list(self.session.scalars(select(JobModel).order_by(JobModel.discovered_at.desc())))

    def create_job(self, values: dict[str, object]) -> JobModel:
        job = JobModel(**values)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def update_job(self, job_id: str, values: dict[str, object]) -> JobModel:
        job = self.get_job(job_id)
        for name, value in values.items():
            setattr(job, name, value)
        self.session.commit()
        self.session.refresh(job)
        return job

    def delete_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        self.session.delete(job)
        self.session.commit()

    def add_source_record(self, job_id: str, values: dict[str, object]) -> JobSourceRecordModel:
        self.get_job(job_id)  # Validate job exists
        source_record = JobSourceRecordModel(job_id=job_id, **values)
        self.session.add(source_record)
        self.session.commit()
        self.session.refresh(source_record)
        return source_record

    def list_source_records(self, job_id: str) -> list[JobSourceRecordModel]:
        self.get_job(job_id)  # Validate job exists
        statement = select(JobSourceRecordModel).where(JobSourceRecordModel.job_id == job_id)
        return list(self.session.scalars(statement.order_by(JobSourceRecordModel.discovered_at.desc())))

    def add_requirement(self, job_id: str, values: dict[str, object]) -> JobRequirementModel:
        self.get_job(job_id)  # Validate job exists
        requirement = JobRequirementModel(job_id=job_id, **values)
        self.session.add(requirement)
        self.session.commit()
        self.session.refresh(requirement)
        return requirement

    def list_requirements(self, job_id: str) -> list[JobRequirementModel]:
        self.get_job(job_id)  # Validate job exists
        statement = select(JobRequirementModel).where(JobRequirementModel.job_id == job_id)
        return list(self.session.scalars(statement))

    def add_evaluation(self, job_id: str, profile_id: str, values: dict[str, object]) -> JobEvaluationModel:
        self.get_job(job_id)  # Validate job exists
        # In a real implementation, we would also validate the profile exists
        evaluation = JobEvaluationModel(job_id=job_id, profile_id=profile_id, **values)
        self.session.add(evaluation)
        self.session.commit()
        self.session.refresh(evaluation)
        return evaluation

    def get_latest_evaluation(self, job_id: str, profile_id: str) -> JobEvaluationModel | None:
        self.get_job(job_id)  # Validate job exists
        statement = select(JobEvaluationModel).where(
            JobEvaluationModel.job_id == job_id,
            JobEvaluationModel.profile_id == profile_id
        ).order_by(JobEvaluationModel.created_at.desc())
        return self.session.scalars(statement).first()

    def list_evaluations(self, job_id: str) -> list[JobEvaluationModel]:
        self.get_job(job_id)  # Validate job exists
        statement = select(JobEvaluationModel).where(JobEvaluationModel.job_id == job_id)
        return list(self.session.scalars(statement.order_by(JobEvaluationModel.created_at.desc())))

    def update_job_status(self, job_id: str, new_status: str, actor: str | None = None, reason: str | None = None) -> JobModel:
        """Update job status and track the change in history."""
        job = self.get_job(job_id)
        old_status = job.status
        
        # Only create history entry if status actually changed
        if old_status != new_status:
            # Create status history entry
            history_entry = JobStatusHistoryModel(
                job_id=job_id,
                old_status=old_status,
                new_status=new_status,
                actor=actor,
                reason=reason
            )
            self.session.add(history_entry)
        
        # Update job status
        job.status = new_status
        self.session.commit()
        self.session.refresh(job)
        return job

    def shortlist_job(self, job_id: str, actor: str | None = None, reason: str | None = None) -> JobModel:
        """Shortlist a job."""
        return self.update_job_status(job_id, "SHORTLISTED", actor, reason or "Job shortlisted by user")

    def reject_job(self, job_id: str, actor: str | None = None, reason: str | None = None) -> JobModel:
        """Reject a job."""
        return self.update_job_status(job_id, "REJECTED", actor, reason or "Job rejected by user")

    def save_job(self, job_id: str, actor: str | None = None, reason: str | None = None) -> JobModel:
        """Save a job."""
        return self.update_job_status(job_id, "SAVED", actor, reason or "Job saved by user")

    def archive_job(self, job_id: str, actor: str | None = None, reason: str | None = None) -> JobModel:
        """Archive a job."""
        return self.update_job_status(job_id, "ARCHIVED", actor, reason or "Job archived by user")

    def add_profile_item(
        self, model: type[T], job_id: str, values: dict[str, object]
    ) -> T:
        self.get_job(job_id)
        item = model(job_id=job_id, **values)  # type: ignore[call-arg]
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def list_profile_items(self, model: type[T], job_id: str) -> list[T]:
        self.get_job(job_id)
        job_column = model.job_id  # type: ignore[attr-defined]
        return list(self.session.scalars(select(model).where(job_column == job_id)))


class JobNotFoundError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Job not found: {job_id}")