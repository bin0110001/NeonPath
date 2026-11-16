"""Build, render, version and retrieve artifacts. Always profile-scoped."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerflow.application.applications.resume import ResumeService
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.artifacts.ports import (
    AchievementBlock,
    ContactBlock,
    EducationBlock,
    ExperienceBlock,
    ResumeDocument,
    redact,
)
from careerflow.infrastructure.artifacts.registry import get_renderer
from careerflow.infrastructure.database.models import (
    AchievementModel,
    ArtifactModel,
    EducationModel,
    ExperienceModel,
    JobModel,
    ProfileContactModel,
    ProfileSkillModel,
    SkillModel,
)

KINDS = ("resume", "resume_with_cover_notes")


class ArtifactError(ValueError):
    pass


@dataclass
class Rerender:
    artifact: ArtifactModel
    content: bytes
    matches_stored: bool


def _dates(start: Any, end: Any) -> str:
    if not start and not end:
        return ""
    return f"{start.year if start else ''} - {end.year if end else 'present'}"


class ArtifactService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.profiles = ProfileService(session)
        self.resume = ResumeService(session)

    # -- building the generation input -----------------------------------------------------

    def build_document(self, profile_id: str, job_id: str | None, redacted: bool, with_cover_notes: bool) -> tuple[ResumeDocument, str | None]:
        """Assemble the document from the profile's own records and its approved package.
        Facts are copied, never rewritten; returns (document, package_id)."""
        profile = self.profiles.get_profile(profile_id)
        job = None
        if job_id is not None:
            job = self.session.get(JobModel, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
        package = self.resume.package_for_job(profile_id, job_id) if job_id else None
        approved = package if package is not None and package.status == "APPROVED" else None
        variant = self.resume.get_variant(profile_id, package.resume_variant_id) if package and package.resume_variant_id else None

        experiences = list(self.session.scalars(select(ExperienceModel).where(ExperienceModel.profile_id == profile_id).order_by(ExperienceModel.sort_order)))
        if variant and variant.selected_experience_ids:
            experiences = [e for e in experiences if e.id in set(variant.selected_experience_ids)]
        achievements = list(self.session.scalars(select(AchievementModel).where(AchievementModel.profile_id == profile_id)))
        chosen = (approved.recommended_achievement_ids if approved else None) or (variant.selected_achievement_ids if variant else None)
        if chosen:
            order = {a_id: i for i, a_id in enumerate(chosen)}
            achievements = sorted((a for a in achievements if a.id in order), key=lambda a: order[a.id])

        skill_rows = self.session.execute(
            select(ProfileSkillModel, SkillModel).join(SkillModel, SkillModel.id == ProfileSkillModel.skill_id).where(ProfileSkillModel.profile_id == profile_id)
        ).all()
        by_years = [s.canonical_name for link, s in sorted(skill_rows, key=lambda r: (-(r[0].years_experience or 0), r[1].canonical_name))]
        skills = tuple(approved.recommended_skill_order if approved and approved.recommended_skill_order else by_years)

        contact_row = self.session.get(ProfileContactModel, profile_id)
        contact = None
        if contact_row is not None:
            place = ", ".join(p for p in (contact_row.city, contact_row.region, contact_row.country) if p)
            contact = ContactBlock(
                full_name=contact_row.full_name, email=contact_row.email, phone=contact_row.phone,
                location=place or None,
                links=tuple(x for x in (contact_row.website, contact_row.linkedin_url, contact_row.github_url) if x),
            )  # fmt: skip
        document = ResumeDocument(
            name=(contact_row.full_name if contact_row and contact_row.full_name else profile.display_name),
            headline=profile.headline,
            summary=(approved.summary_suggestion if approved and approved.summary_suggestion else profile.summary),
            contact=contact,
            skills=skills,
            experiences=tuple(
                ExperienceBlock(e.title, e.organization, _dates(e.start_date, e.end_date), e.location, e.description) for e in experiences
            ),
            achievements=tuple(
                AchievementBlock(
                    a.title, " ".join(filter(None, [a.situation, a.action, a.result])), tuple(a.technologies or []), a.verified
                )
                for a in achievements
            ),
            education=tuple(
                EducationBlock(ed.institution, ed.degree, ed.field_of_study, _dates(ed.start_date, ed.end_date))
                for ed in self.session.scalars(select(EducationModel).where(EducationModel.profile_id == profile_id))
            ),
            cover_letter_notes=tuple(approved.cover_letter_notes) if approved and with_cover_notes else (),
            target=f"{job.title} at {job.company}" if job else None,
        )
        return (redact(document) if redacted else document), (package.id if package else None)

    # -- creating versions -----------------------------------------------------------------

    def create(self, profile_id: str, job_id: str | None, fmt: str, redacted: bool = False, with_cover_notes: bool = False, kind: str | None = None) -> ArtifactModel:
        renderer = get_renderer(fmt)  # UnknownFormatError -> caller
        kind = kind or ("resume_with_cover_notes" if with_cover_notes else "resume")
        if kind not in KINDS:
            raise ArtifactError(f"kind must be one of {KINDS}")
        document, package_id = self.build_document(profile_id, job_id, redacted, with_cover_notes)
        content = renderer.render(document)
        latest = self.session.scalar(
            select(func.max(ArtifactModel.version)).where(
                ArtifactModel.profile_id == profile_id,
                ArtifactModel.job_id.is_(job_id) if job_id is None else ArtifactModel.job_id == job_id,
                ArtifactModel.kind == kind,
                ArtifactModel.format == fmt,
            )
        )
        row = ArtifactModel(
            profile_id=profile_id, job_id=job_id, kind=kind, format=fmt, version=(latest or 0) + 1,
            renderer_version=renderer.version, redacted=redacted, input_json=document.to_json(),
            content=content, content_sha256=hashlib.sha256(content).hexdigest(), package_id=package_id,
        )  # fmt: skip
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    # -- reading ---------------------------------------------------------------------------

    def list(self, profile_id: str, job_id: str | None = None) -> list[ArtifactModel]:
        self.profiles.get_profile(profile_id)
        statement = select(ArtifactModel).where(ArtifactModel.profile_id == profile_id).order_by(ArtifactModel.created_at.desc(), ArtifactModel.version.desc())
        if job_id:
            statement = statement.where(ArtifactModel.job_id == job_id)
        return list(self.session.scalars(statement))

    def get(self, profile_id: str, artifact_id: str) -> ArtifactModel:
        return self.profiles.get_profile_item(ArtifactModel, profile_id, artifact_id)

    def rerender(self, profile_id: str, artifact_id: str) -> Rerender:
        """Regenerate an old version from its retained inputs and compare with what was delivered."""
        artifact = self.get(profile_id, artifact_id)
        renderer = get_renderer(artifact.format)
        content = renderer.render(ResumeDocument.from_json(artifact.input_json))
        return Rerender(artifact, content, hashlib.sha256(content).hexdigest() == artifact.content_sha256)
