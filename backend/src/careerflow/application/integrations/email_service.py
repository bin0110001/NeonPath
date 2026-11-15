"""Email: recognise and link messages to applications; draft replies locally. Never sends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.profiles.service import ProfileService
from careerflow.domain.integrations.matching import ApplicationFacts, classify_email, match_email
from careerflow.domain.integrations.ports import EmailMessage, EmailProvider
from careerflow.infrastructure.database.models import (
    ApplicationContactModel,
    ApplicationModel,
    ContactModel,
    EmailDraftModel,
    EmailLinkModel,
    JobModel,
)

DRAFT_NOTICE = "[DRAFT for you to review and send yourself. CareerFlow never sends email.]"
LOOKBACK = timedelta(days=30)

TEMPLATES: dict[str, str] = {
    "interview_request": (
        "Hello,\n\nThank you for reaching out about the {title} role. I'd be glad to talk. "
        "I am available [your availability here]. Please let me know what works for you and "
        "whether there is anything I should prepare.\n\nBest regards,\n{name}"
    ),
    "rejection": (
        "Hello,\n\nThank you for letting me know and for the time you spent on my application for "
        "the {title} role. If you are able to share any feedback, I would appreciate it, and I'd "
        "welcome being considered for future openings.\n\nBest regards,\n{name}"
    ),
    "offer": (
        "Hello,\n\nThank you very much for the offer for the {title} role. I'm excited about it. "
        "Could you share the full details in writing and the date by which you need my answer? "
        "I will respond promptly.\n\nBest regards,\n{name}"
    ),
    "recruiter_outreach": (
        "Hello,\n\nThank you for getting in touch. [I'm interested / I'm not looking right now]. "
        "Could you share the role description, location and compensation range?\n\n"
        "Best regards,\n{name}"
    ),
    "other": "Hello,\n\nThank you for your message. [your reply here]\n\nBest regards,\n{name}",
}


@dataclass
class SyncResult:
    scanned: int = 0
    linked: int = 0
    unmatched: int = 0
    skipped_known: int = 0


class EmailService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.profiles = ProfileService(session)

    def _facts(self, profile_id: str) -> list[ApplicationFacts]:
        facts = []
        for app, job in self.session.execute(
            select(ApplicationModel, JobModel).join(JobModel, JobModel.id == ApplicationModel.job_id).where(ApplicationModel.profile_id == profile_id)
        ):
            emails = tuple(
                c.email
                for c in self.session.scalars(
                    select(ContactModel)
                    .join(ApplicationContactModel, ApplicationContactModel.contact_id == ContactModel.id)
                    .where(ApplicationContactModel.application_id == app.id)
                )
                if c.email
            )
            threads = tuple(
                t for t in self.session.scalars(
                    select(EmailLinkModel.thread_id).where(
                        EmailLinkModel.application_id == app.id, EmailLinkModel.status != "DISMISSED"
                    )
                ) if t
            )
            facts.append(ApplicationFacts(app.id, job.company, job.title, job.company_domain, emails, threads))
        return facts

    def sync(self, profile_id: str, provider: EmailProvider, since: datetime | None = None, limit: int = 50) -> SyncResult:
        """Read recent messages and store only recognised ones as links (ids, no content)."""
        self.profiles.get_profile(profile_id)
        facts = self._facts(profile_id)
        known = set(self.session.scalars(select(EmailLinkModel.message_id).where(EmailLinkModel.profile_id == profile_id)))
        result = SyncResult()
        for message in provider.list_messages(since or datetime.now(UTC) - LOOKBACK, limit):
            result.scanned += 1
            if message.id in known:
                result.skipped_known += 1
                continue
            link = self._link_for(profile_id, message, facts)
            if link is None:
                continue
            self.session.add(link)
            self.session.flush()
            known.add(message.id)
            if link.application_id:
                result.linked += 1
                facts = self._facts(profile_id)  # thread ids of the new link help the next messages
            else:
                result.unmatched += 1
        self.session.commit()
        return result

    @staticmethod
    def _link_for(profile_id: str, message: EmailMessage, facts: list[ApplicationFacts]) -> EmailLinkModel | None:
        classification = classify_email(message)
        candidates = match_email(message, facts)
        best = candidates[0] if candidates else None
        if best is None and classification.kind == "other":
            return None  # unrelated mail is not recorded at all
        return EmailLinkModel(
            profile_id=profile_id,
            application_id=best.application_id if best else None,
            message_id=message.id,
            thread_id=message.thread_id,
            sender_domain=message.sender.rsplit("@", 1)[-1] if "@" in message.sender else None,
            classification=classification.kind,
            score=best.score if best else 0.0,
            reasons=[*(best.reasons if best else []), *classification.reasons],
            received_at=message.received_at,
            status="SUGGESTED",
        )

    # -- review ---------------------------------------------------------------------------------

    def list_links(self, profile_id: str, status: str | None = None) -> list[EmailLinkModel]:
        self.profiles.get_profile(profile_id)
        statement = select(EmailLinkModel).where(EmailLinkModel.profile_id == profile_id).order_by(EmailLinkModel.received_at.desc())
        if status:
            statement = statement.where(EmailLinkModel.status == status)
        return list(self.session.scalars(statement))

    def confirm(self, profile_id: str, link_id: str, application_id: str | None = None) -> EmailLinkModel:
        link = self.profiles.get_profile_item(EmailLinkModel, profile_id, link_id)
        if application_id is not None:
            self.profiles.get_profile_item(ApplicationModel, profile_id, application_id)  # must be this profile's
            link.application_id = application_id
        if link.application_id is None:
            raise ValueError("choose an application to link this message to")
        link.status = "CONFIRMED"
        self.session.commit()
        return link

    def dismiss(self, profile_id: str, link_id: str) -> EmailLinkModel:
        link = self.profiles.get_profile_item(EmailLinkModel, profile_id, link_id)
        link.status = "DISMISSED"
        self.session.commit()
        return link

    # -- drafts (local only) ------------------------------------------------------------------------

    def draft_reply(self, profile_id: str, link_id: str) -> EmailDraftModel:
        link = self.profiles.get_profile_item(EmailLinkModel, profile_id, link_id)
        profile = self.profiles.get_profile(profile_id)
        title = "this"
        if link.application_id:
            row = self.session.execute(
                select(JobModel.title).join(ApplicationModel, ApplicationModel.job_id == JobModel.id).where(ApplicationModel.id == link.application_id)
            ).first()
            title = row[0] if row else title
        body = TEMPLATES.get(link.classification, TEMPLATES["other"]).format(title=title, name=profile.display_name)
        draft = EmailDraftModel(profile_id=profile_id, link_id=link.id, body=f"{DRAFT_NOTICE}\n\n{body}")
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def drafts(self, profile_id: str, link_id: str) -> list[EmailDraftModel]:
        self.profiles.get_profile_item(EmailLinkModel, profile_id, link_id)
        return list(self.session.scalars(select(EmailDraftModel).where(EmailDraftModel.link_id == link_id).order_by(EmailDraftModel.created_at.desc())))


