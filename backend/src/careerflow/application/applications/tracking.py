"""Application tracking: records, contacts, follow-ups, interviews, pipeline and metrics.

Everything is scoped by ``profile_id``: a record id owned by another profile behaves as
if it does not exist. The pipeline is driven by the workflow state machine, so moving a
card is a validated transition that writes history.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.applications.resume import ResumeService
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.jobs.workflow import JobWorkflowService
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileService
from careerflow.domain.applications.metrics import FunnelMetrics, Transition, compute_metrics
from careerflow.domain.jobs.workflow import WorkflowStatus, parse_status
from careerflow.infrastructure.database.models import (
    ApplicationContactModel,
    ApplicationModel,
    ContactModel,
    FollowUpModel,
    InterviewModel,
    JobEvaluationModel,
    JobModel,
    JobStatusHistoryModel,
    ProfileJobModel,
)

CONTACT_ROLES = frozenset({"recruiter", "hiring_manager", "referral", "interviewer", "other"})
INTERVIEW_TYPES = frozenset(
    {"recruiter", "hiring_manager", "coding", "system_design", "machine_learning", "architecture",
     "behavioral", "panel", "executive", "other"}  # fmt: skip
)
INTERVIEW_OUTCOMES = frozenset({"PENDING", "PASSED", "FAILED", "UNKNOWN"})
FOLLOW_UP_STATUSES = frozenset({"OPEN", "DONE", "DISMISSED"})

# Columns of the pipeline board, in funnel order. READY_FOR_REVIEW/SAVED/ARCHIVED are inbox states.
PIPELINE_COLUMNS: tuple[WorkflowStatus, ...] = (
    WorkflowStatus.SHORTLISTED,
    WorkflowStatus.PREPARING,
    WorkflowStatus.READY_TO_APPLY,
    WorkflowStatus.APPLIED,
    WorkflowStatus.SCREENING,
    WorkflowStatus.INTERVIEWING,
    WorkflowStatus.FINAL,
    WorkflowStatus.OFFER,
    WorkflowStatus.REJECTED,
    WorkflowStatus.WITHDRAWN,
)


class TrackingError(ValueError):
    """A request that is well-formed but not allowed (bad enum value, foreign record, ...)."""


@dataclass
class Card:
    job_id: str
    title: str
    company: str
    status: str
    score: float | None
    application_id: str | None
    applied_at: datetime | None
    next_follow_up_at: datetime | None
    next_interview_at: datetime | None


@dataclass
class Overview:
    due_follow_ups: list[FollowUpModel]
    upcoming_interviews: list[InterviewModel]
    metrics: FunnelMetrics


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class TrackingService:
    def __init__(self, session: Session, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.session = session
        self.clock = clock
        self.profiles = ProfileService(session)
        self.workflow = JobWorkflowService(session)

    # -- applications -----------------------------------------------------------------------

    def _check_application(self, profile_id: str, values: dict[str, Any]) -> None:
        if values.get("resume_variant_id"):
            ResumeService(self.session).get_variant(profile_id, values["resume_variant_id"])

    def list_applications(self, profile_id: str) -> list[ApplicationModel]:
        return self.profiles.list_profile_items(ApplicationModel, profile_id)

    def get_application(self, profile_id: str, application_id: str) -> ApplicationModel:
        return self.profiles.get_profile_item(ApplicationModel, profile_id, application_id)

    def application_for_job(self, profile_id: str, job_id: str) -> ApplicationModel | None:
        return self.session.scalars(
            select(ApplicationModel).where(ApplicationModel.profile_id == profile_id, ApplicationModel.job_id == job_id)
        ).first()

    def create_application(self, profile_id: str, values: dict[str, Any]) -> ApplicationModel:
        self.profiles.get_profile(profile_id)
        if self.session.get(JobModel, values["job_id"]) is None:
            raise JobNotFoundError(values["job_id"])
        if self.application_for_job(profile_id, values["job_id"]) is not None:
            raise TrackingError("an application for this job already exists")
        self._check_application(profile_id, values)
        return self.profiles.add_profile_item(ApplicationModel, profile_id, values)

    def update_application(self, profile_id: str, application_id: str, values: dict[str, Any]) -> ApplicationModel:
        values = {k: v for k, v in values.items() if k != "job_id"}  # the job cannot be changed
        self._check_application(profile_id, values)
        return self.profiles.update_profile_item(ApplicationModel, profile_id, application_id, values)

    def delete_application(self, profile_id: str, application_id: str) -> None:
        self.get_application(profile_id, application_id)
        for model in (ApplicationContactModel,):
            for row in self.session.scalars(select(model).where(model.application_id == application_id)):
                self.session.delete(row)
        for model2 in (FollowUpModel, InterviewModel):
            for row2 in self.session.scalars(select(model2).where(model2.application_id == application_id)):
                self.session.delete(row2)
        self.session.flush()
        self.profiles.delete_profile_item(ApplicationModel, profile_id, application_id)

    # -- contacts ---------------------------------------------------------------------------

    def link_contact(self, profile_id: str, application_id: str, contact_id: str, role: str) -> ApplicationContactModel:
        if role not in CONTACT_ROLES:
            raise TrackingError(f"role must be one of {sorted(CONTACT_ROLES)}")
        self.get_application(profile_id, application_id)
        self.profiles.get_profile_item(ContactModel, profile_id, contact_id)
        link = self.session.get(ApplicationContactModel, (application_id, contact_id))
        if link is None:
            link = ApplicationContactModel(application_id=application_id, contact_id=contact_id, role=role)
            self.session.add(link)
        else:
            link.role = role
        self.session.commit()
        return link

    def unlink_contact(self, profile_id: str, application_id: str, contact_id: str) -> None:
        self.get_application(profile_id, application_id)
        link = self.session.get(ApplicationContactModel, (application_id, contact_id))
        if link is None:
            raise ProfileItemNotFoundError(contact_id)
        self.session.delete(link)
        self.session.commit()

    def application_contacts(self, profile_id: str, application_id: str) -> list[ApplicationContactModel]:
        self.get_application(profile_id, application_id)
        return list(
            self.session.scalars(select(ApplicationContactModel).where(ApplicationContactModel.application_id == application_id))
        )

    def delete_contact(self, profile_id: str, contact_id: str) -> None:
        self.profiles.get_profile_item(ContactModel, profile_id, contact_id)
        for link in self.session.scalars(
            select(ApplicationContactModel).where(ApplicationContactModel.contact_id == contact_id)
        ):
            self.session.delete(link)
        self.session.flush()
        self.profiles.delete_profile_item(ContactModel, profile_id, contact_id)

    # -- follow-ups ---------------------------------------------------------------------------

    def create_follow_up(self, profile_id: str, values: dict[str, Any]) -> FollowUpModel:
        self.get_application(profile_id, values["application_id"])
        return self.profiles.add_profile_item(FollowUpModel, profile_id, values)

    def set_follow_up_status(self, profile_id: str, follow_up_id: str, status: str) -> FollowUpModel:
        if status not in FOLLOW_UP_STATUSES:
            raise TrackingError(f"status must be one of {sorted(FOLLOW_UP_STATUSES)}")
        row = self.profiles.get_profile_item(FollowUpModel, profile_id, follow_up_id)
        row.status = status
        row.completed_at = self.clock() if status != "OPEN" else None
        self.session.commit()
        return row

    def follow_ups(self, profile_id: str, status: str | None = None, due_by: datetime | None = None) -> list[FollowUpModel]:
        self.profiles.get_profile(profile_id)
        statement = select(FollowUpModel).where(FollowUpModel.profile_id == profile_id).order_by(FollowUpModel.due_at)
        if status:
            statement = statement.where(FollowUpModel.status == status)
        if due_by:
            statement = statement.where(FollowUpModel.due_at <= due_by)
        return list(self.session.scalars(statement))

    # -- interviews -------------------------------------------------------------------------------

    @staticmethod
    def _check_interview(values: dict[str, Any]) -> None:
        if "type" in values and values["type"] not in INTERVIEW_TYPES:
            raise TrackingError(f"type must be one of {sorted(INTERVIEW_TYPES)}")
        if "outcome" in values and values["outcome"] not in INTERVIEW_OUTCOMES:
            raise TrackingError(f"outcome must be one of {sorted(INTERVIEW_OUTCOMES)}")

    def create_interview(self, profile_id: str, values: dict[str, Any]) -> InterviewModel:
        self._check_interview(values)
        self.get_application(profile_id, values["application_id"])
        return self.profiles.add_profile_item(InterviewModel, profile_id, values)

    def update_interview(self, profile_id: str, interview_id: str, values: dict[str, Any]) -> InterviewModel:
        self._check_interview(values)
        values = {k: v for k, v in values.items() if k != "application_id"}
        return self.profiles.update_profile_item(InterviewModel, profile_id, interview_id, values)

    def interviews(self, profile_id: str, upcoming_only: bool = False, within_days: int | None = None) -> list[InterviewModel]:
        self.profiles.get_profile(profile_id)
        statement = select(InterviewModel).where(InterviewModel.profile_id == profile_id).order_by(InterviewModel.scheduled_at)
        now = self.clock()
        if upcoming_only:
            statement = statement.where(InterviewModel.scheduled_at >= now)
        if within_days is not None:
            statement = statement.where(InterviewModel.scheduled_at <= now + timedelta(days=within_days))
        return list(self.session.scalars(statement))

    # -- pipeline ---------------------------------------------------------------------------------

    def transition(self, profile_id: str, job_id: str, to_status: str, actor: str | None, reason: str | None) -> WorkflowStatus:
        """Validated workflow move (raises InvalidTransitionError); entering APPLIED also
        makes sure an application record exists with its applied date."""
        try:
            target = parse_status(to_status)
        except ValueError as error:
            raise TrackingError(str(error)) from error
        new = self.workflow.transition(profile_id, job_id, target, actor, reason)
        if new is WorkflowStatus.APPLIED and self.application_for_job(profile_id, job_id) is None:
            self.create_application(profile_id, {"job_id": job_id, "applied_at": self.clock()})
        return new

    def pipeline(self, profile_id: str) -> dict[str, list[Card]]:
        self.profiles.get_profile(profile_id)
        wanted = [c.value for c in PIPELINE_COLUMNS]
        rows = self.session.execute(
            select(ProfileJobModel, JobModel)
            .join(JobModel, JobModel.id == ProfileJobModel.job_id)
            .where(ProfileJobModel.profile_id == profile_id, ProfileJobModel.status.in_(wanted), JobModel.merged_into_id.is_(None))
            .order_by(ProfileJobModel.updated_at.desc())
        ).all()
        apps = {a.job_id: a for a in self.list_applications(profile_id)}
        follow_ups: dict[str, datetime] = {}
        for f in self.follow_ups(profile_id, "OPEN"):
            follow_ups.setdefault(f.application_id, _utc(f.due_at))
        interviews: dict[str, datetime] = {}
        for i in self.interviews(profile_id, upcoming_only=True):
            if i.scheduled_at is not None:
                interviews.setdefault(i.application_id, _utc(i.scheduled_at))
        columns: dict[str, list[Card]] = {c: [] for c in wanted}
        for link, job in rows:
            app = apps.get(job.id)
            score = self.session.scalars(
                select(JobEvaluationModel.overall_score)
                .where(JobEvaluationModel.job_id == job.id, JobEvaluationModel.profile_id == profile_id)
                .order_by(JobEvaluationModel.created_at.desc())
            ).first()
            columns[link.status].append(
                Card(
                    job_id=job.id, title=job.title, company=job.company, status=link.status, score=score,
                    application_id=app.id if app else None,
                    applied_at=app.applied_at if app else None,
                    next_follow_up_at=follow_ups.get(app.id) if app else None,
                    next_interview_at=interviews.get(app.id) if app else None,
                )  # fmt: skip
            )
        return columns

    # -- overview / metrics --------------------------------------------------------------------------

    def metrics(self, profile_id: str) -> FunnelMetrics:
        self.profiles.get_profile(profile_id)
        history = self.session.scalars(
            select(JobStatusHistoryModel).where(JobStatusHistoryModel.profile_id == profile_id)
        )
        return compute_metrics(
            [Transition(h.job_id, h.old_status, h.new_status, _utc(h.timestamp)) for h in history]
        )

    def overview(self, profile_id: str, interview_days: int = 14) -> Overview:
        now = self.clock()
        return Overview(
            due_follow_ups=self.follow_ups(profile_id, "OPEN", due_by=now),
            upcoming_interviews=self.interviews(profile_id, upcoming_only=True, within_days=interview_days),
            metrics=self.metrics(profile_id),
        )
