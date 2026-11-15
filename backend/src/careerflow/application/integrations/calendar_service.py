"""Calendar: import interview events (idempotent) and write only with explicit approval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.integrations.accounts import AccountService
from careerflow.application.profiles.service import ProfileService
from careerflow.demo import ensure_external_writes_allowed
from careerflow.domain.integrations.matching import ApplicationFacts, match_event
from careerflow.domain.integrations.ports import (
    CalendarEvent,
    CalendarProvider,
    IntegrationError,
    NewCalendarEvent,
)
from careerflow.infrastructure.database.models import (
    ApplicationContactModel,
    ApplicationModel,
    CalendarWriteRequestModel,
    ContactModel,
    FollowUpModel,
    InterviewModel,
    JobModel,
)
from careerflow.infrastructure.logging import get_redactor
from careerflow.settings import Settings

PREP_LEAD = timedelta(days=1)
PREP_TYPE = "prep"


@dataclass
class ImportResult:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    reminders: int = 0


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class CalendarService:
    def __init__(self, session: Session, settings: Settings | None = None, accounts: AccountService | None = None) -> None:
        self.session = session
        self.settings = settings
        self.accounts = accounts
        self.profiles = ProfileService(session)

    # -- import (read) -----------------------------------------------------------------------------

    def _facts(self, profile_id: str) -> list[ApplicationFacts]:
        out = []
        for app, job in self.session.execute(
            select(ApplicationModel, JobModel).join(JobModel, JobModel.id == ApplicationModel.job_id).where(ApplicationModel.profile_id == profile_id)
        ):
            emails = tuple(
                c.email for c in self.session.scalars(
                    select(ContactModel).join(ApplicationContactModel, ApplicationContactModel.contact_id == ContactModel.id).where(ApplicationContactModel.application_id == app.id)
                ) if c.email
            )
            out.append(ApplicationFacts(app.id, job.company, job.title, job.company_domain, emails))
        return out

    def import_events(self, profile_id: str, provider: CalendarProvider, since: datetime | None = None) -> ImportResult:
        """Create/update interviews for matching events. Safe to repeat: events are keyed by
        their external id, so re-importing never creates duplicates."""
        self.profiles.get_profile(profile_id)
        facts = self._facts(profile_id)
        result = ImportResult()
        for event in provider.list_events(since or datetime.now(UTC) - timedelta(days=1)):
            result.scanned += 1
            candidates = match_event(event, facts)
            existing = self.session.scalars(
                select(InterviewModel).where(InterviewModel.profile_id == profile_id, InterviewModel.external_event_id == event.id)
            ).first()
            if existing is None and not candidates:
                result.unmatched += 1
                continue
            if existing is None:
                interview = InterviewModel(
                    profile_id=profile_id, application_id=candidates[0].application_id, type="other",
                    external_event_id=event.id, outcome="PENDING",
                )  # fmt: skip
                self._apply(interview, event)
                self.session.add(interview)
                self.session.flush()
                result.created += 1
            else:
                interview = existing
                changed = self._apply(interview, event)
                result.updated += 1 if changed else 0
                result.unchanged += 0 if changed else 1
            if self._ensure_reminder(profile_id, interview):
                result.reminders += 1
        self.session.commit()
        if self.accounts:
            self.accounts.mark_synced(profile_id, "calendar")
        return result

    @staticmethod
    def _apply(interview: InterviewModel, event: CalendarEvent) -> bool:
        duration = int((event.ends_at - event.starts_at).total_seconds() // 60) if event.ends_at else None
        new = {
            "scheduled_at": event.starts_at, "duration_minutes": duration, "participants": list(event.attendees),
            "meeting_url": event.meeting_url,
        }  # fmt: skip
        current = {
            "scheduled_at": _utc(interview.scheduled_at) if interview.scheduled_at else None,
            "duration_minutes": interview.duration_minutes, "participants": list(interview.participants or []),
            "meeting_url": interview.meeting_url,
        }  # fmt: skip
        changed = {k: v for k, v in new.items() if current[k] != (_utc(v) if isinstance(v, datetime) else v)}
        for key, value in new.items():
            setattr(interview, key, value)
        return bool(changed)

    def _ensure_reminder(self, profile_id: str, interview: InterviewModel) -> bool:
        if interview.scheduled_at is None:
            return False
        marker = f"interview:{interview.id}"
        due = _utc(interview.scheduled_at) - PREP_LEAD
        existing = self.session.scalars(
            select(FollowUpModel).where(FollowUpModel.application_id == interview.application_id, FollowUpModel.type == PREP_TYPE, FollowUpModel.notes == marker)
        ).first()
        if existing is not None:
            if existing.status == "OPEN":
                existing.due_at = due  # keep the reminder aligned if the event moved
            return False
        self.session.add(
            FollowUpModel(profile_id=profile_id, application_id=interview.application_id, due_at=due, type=PREP_TYPE, notes=marker)
        )
        return True

    # -- writes (approval-gated) ----------------------------------------------------------------------

    def propose(self, profile_id: str, interview_id: str) -> CalendarWriteRequestModel:
        """Record the change we would make. Writes nothing externally."""
        interview = self.profiles.get_profile_item(InterviewModel, profile_id, interview_id)
        if interview.scheduled_at is None:
            raise ValueError("the interview has no scheduled time")
        app = self.profiles.get_profile_item(ApplicationModel, profile_id, interview.application_id)
        job = self.session.get(JobModel, app.job_id)
        title = f"Interview: {job.title} at {job.company}" if job else "Interview"
        start = _utc(interview.scheduled_at)
        end = start + timedelta(minutes=interview.duration_minutes or 60)
        request = CalendarWriteRequestModel(
            profile_id=profile_id,
            interview_id=interview.id,
            action="update" if interview.external_event_id else "create",
            event_id=interview.external_event_id,
            payload_json={
                "title": title, "starts_at": start.isoformat(), "ends_at": end.isoformat(),
                "attendees": list(interview.participants or []), "description": interview.notes or "",
            },  # fmt: skip
        )
        self.session.add(request)
        self.session.commit()
        self.session.refresh(request)
        return request

    def requests(self, profile_id: str, status: str | None = None) -> list[CalendarWriteRequestModel]:
        self.profiles.get_profile(profile_id)
        statement = select(CalendarWriteRequestModel).where(CalendarWriteRequestModel.profile_id == profile_id).order_by(CalendarWriteRequestModel.created_at.desc())
        if status:
            statement = statement.where(CalendarWriteRequestModel.status == status)
        return list(self.session.scalars(statement))

    def reject(self, profile_id: str, request_id: str) -> CalendarWriteRequestModel:
        request = self.profiles.get_profile_item(CalendarWriteRequestModel, profile_id, request_id)
        if request.status != "PENDING":
            raise ValueError(f"request is already {request.status}")
        request.status, request.decided_at = "REJECTED", datetime.now(UTC)
        self.session.commit()
        return request

    def approve(self, profile_id: str, request_id: str, provider: CalendarProvider, writes_allowed: bool) -> CalendarWriteRequestModel:
        """The ONLY place a provider write happens, and only for a PENDING request the user approved."""
        request = self.profiles.get_profile_item(CalendarWriteRequestModel, profile_id, request_id)
        if request.status != "PENDING":
            raise ValueError(f"request is already {request.status}")
        ensure_external_writes_allowed(self.settings)  # demo mode: never write externally
        if not writes_allowed:
            raise IntegrationError("this calendar connection is read-only; reconnect with write access to create events")
        request.status, request.decided_at = "APPROVED", datetime.now(UTC)
        self.session.commit()
        payload: dict[str, Any] = request.payload_json
        event = NewCalendarEvent(
            title=payload["title"],
            starts_at=datetime.fromisoformat(payload["starts_at"]),
            ends_at=datetime.fromisoformat(payload["ends_at"]),
            attendees=tuple(payload.get("attendees", ())),
            description=payload.get("description", ""),
        )
        try:
            if request.action == "update" and request.event_id:
                provider.update_event(request.event_id, event)
            else:
                new_id = provider.create_event(event)
                if request.interview_id:
                    interview = self.session.get(InterviewModel, request.interview_id)
                    if interview is not None:
                        interview.external_event_id = new_id  # so a later import recognises it
        except IntegrationError as error:
            request.status, request.error = "FAILED", get_redactor().redact(str(error))[:500]
        else:
            request.status = "DONE"
        self.session.commit()
        return request
