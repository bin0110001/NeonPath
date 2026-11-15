"""Application preparation: propose, review, approve (plan sections 4.4, 4.5, 13).

``propose`` never writes anything. The user reviews the proposal (and may edit it) and
only ``approve`` persists it. Nothing in this module can send a message or contact anyone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.ai.client import AiClient
from careerflow.application.applications.resume import ResumeService
from careerflow.application.evaluations.mappers import load_skill_catalog
from careerflow.application.evaluations.semantic import collect_evidence
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.ai.ports import AiError, AiUnavailableError
from careerflow.domain.applications.tailoring import (
    TAILOR_VERSION,
    AchievementFact,
    JobFacts,
    Note,
    SkillFact,
    VariantFact,
    recommend,
)
from careerflow.domain.evaluations.semantic import Claim, validate_claims
from careerflow.infrastructure.database.models import (
    AchievementModel,
    ApplicationPackageModel,
    JobModel,
    ProfileSkillModel,
    ResumeVariantModel,
    RoleFamilyModel,
    SkillAliasModel,
    SkillModel,
)

PROMPT_KEY = "application_prep"
OUTREACH_DISCLAIMER = "DRAFT for your review. CareerFlow never sends messages."


class CoverPointOut(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(default_factory=list)


class ApplicationPrepOut(BaseModel):
    summary_suggestion: str = ""
    cover_letter_points: list[CoverPointOut] = Field(default_factory=list)
    outreach_draft: str = ""


@dataclass
class ProposalClaim:
    text: str
    basis: str  # evidence | inference | unverified
    evidence_ids: list[str]
    source: str  # deterministic | ai
    note: str | None = None


@dataclass
class Proposal:
    job_id: str
    profile_id: str
    resume_variant_id: str | None
    recommended_achievement_ids: list[str]
    recommended_skill_order: list[str]
    summary_suggestion: str | None
    tailoring_notes: list[str]
    cover_letter_notes: list[str]
    missing_evidence: list[str]
    outreach_draft: str | None
    warnings: list[str]
    claims: list[ProposalClaim]
    provenance: dict[str, Any]
    persisted: bool = False
    ai_note: str | None = None
    existing_package_id: str | None = field(default=None)


class PreparationService:
    def __init__(self, session: Session, ai: AiClient | None = None) -> None:
        self.session = session
        self.ai = ai
        self.resume = ResumeService(session)

    # -- facts ------------------------------------------------------------------------------

    def _facts(self, profile_id: str) -> tuple[list[SkillFact], list[AchievementFact], list[VariantFact]]:
        aliases: dict[str, list[str]] = {}
        for alias in self.session.scalars(select(SkillAliasModel)):
            aliases.setdefault(alias.skill_id, []).append(alias.alias)
        skills = [
            SkillFact(
                id=skill.id, name=skill.canonical_name, aliases=tuple(aliases.get(skill.id, [])),
                category=skill.category, years=link.years_experience, verified=link.verified,
            )  # fmt: skip
            for link, skill in self.session.execute(
                select(ProfileSkillModel, SkillModel)
                .join(SkillModel, SkillModel.id == ProfileSkillModel.skill_id)
                .where(ProfileSkillModel.profile_id == profile_id)
            )
        ]
        achievements = [
            AchievementFact(
                id=a.id, title=a.title, text=" ".join(filter(None, [a.situation, a.action, a.result])),
                technologies=tuple(a.technologies or []), tags=tuple(a.competency_tags or []), verified=a.verified,
            )  # fmt: skip
            for a in self.session.scalars(select(AchievementModel).where(AchievementModel.profile_id == profile_id))
        ]
        family_names = {
            f.id: f.name for f in self.session.scalars(select(RoleFamilyModel).where(RoleFamilyModel.profile_id == profile_id))
        }
        variants = [
            VariantFact(
                id=v.id, name=v.name, role_family=family_names.get(v.role_family_id or ""),
                skill_categories=tuple(v.preferred_skill_categories or []),
                achievement_ids=tuple(v.selected_achievement_ids or []),
            )  # fmt: skip
            for v in self.session.scalars(select(ResumeVariantModel).where(ResumeVariantModel.profile_id == profile_id))
        ]
        return skills, achievements, variants

    # -- propose (read-only) ------------------------------------------------------------------

    def propose(self, profile_id: str, job_id: str) -> Proposal:
        self.resume.profiles.get_profile(profile_id)
        job = self.session.get(JobModel, job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        skills, achievements, variants = self._facts(profile_id)
        catalog = [s.name for s in load_skill_catalog(self.session)]
        required = tuple(
            r.normalized_text for r in job.requirements if r.type == "skill" and (r.required_level or "REQUIRED") == "REQUIRED"
        )
        preferred = tuple(r.normalized_text for r in job.requirements if r.type == "skill" and r.required_level == "PREFERRED")
        facts = JobFacts(job.title, job.description_text, required, preferred)
        rec = recommend(facts, skills, achievements, variants, catalog)

        claims = [self._claim(n) for n in [*rec.tailoring_notes, *rec.cover_letter_notes]]
        proposal = Proposal(
            job_id=job_id,
            profile_id=profile_id,
            resume_variant_id=rec.variant_id,
            recommended_achievement_ids=rec.achievement_ids,
            recommended_skill_order=rec.skill_order,
            summary_suggestion=rec.summary_suggestion,
            tailoring_notes=[n.text for n in rec.tailoring_notes],
            cover_letter_notes=[n.text for n in rec.cover_letter_notes],
            missing_evidence=rec.missing_evidence,
            outreach_draft=None,
            warnings=rec.warnings,
            claims=claims,
            provenance={"generator": "deterministic", "version": TAILOR_VERSION},
        )
        existing = self.resume.package_for_job(profile_id, job_id)
        proposal.existing_package_id = existing.id if existing else None
        self._add_ai(proposal, job, profile_id)
        return proposal

    @staticmethod
    def _claim(note: Note) -> ProposalClaim:
        # deterministic notes cite records they were computed from; ones with none are advice only
        basis = "evidence" if note.evidence_ids else "inference"
        return ProposalClaim(note.text, basis, list(note.evidence_ids), "deterministic")

    def _add_ai(self, proposal: Proposal, job: JobModel, profile_id: str) -> None:
        if self.ai is None:
            proposal.ai_note = "AI is not configured: showing deterministic recommendations only."
            return
        evidence = collect_evidence(self.session, profile_id)
        try:
            result = self.ai.run(
                PROMPT_KEY,
                {
                    "title": job.title,
                    "company": job.company,
                    "description": job.description_text,
                    "evidence": "\n".join(f"{i}: {t}" for i, t in evidence.items()) or "(none)",
                },
                ApplicationPrepOut,
            )
        except AiUnavailableError:
            proposal.ai_note = "AI is disabled: showing deterministic recommendations only."
            return
        except AiError as error:  # the deterministic proposal is still useful
            proposal.ai_note = f"AI drafting failed ({type(error).__name__}); showing deterministic recommendations only."
            return
        checked = validate_claims(
            [Claim(p.text, "strength", "evidence", tuple(p.evidence_ids)) for p in result.value.cover_letter_points],
            set(evidence),
        )
        for claim in checked:
            proposal.claims.append(ProposalClaim(claim.text, claim.basis, list(claim.evidence_ids), "ai", claim.note))
            suffix = "" if claim.basis == "evidence" else f" [{claim.basis}: not backed by your profile]"
            proposal.cover_letter_notes.append(claim.text + suffix)
        if result.value.outreach_draft.strip():
            proposal.outreach_draft = f"{result.value.outreach_draft.strip()}\n\n[{OUTREACH_DISCLAIMER}]"
        if result.value.summary_suggestion.strip() and not proposal.summary_suggestion:
            proposal.summary_suggestion = result.value.summary_suggestion.strip()
        proposal.provenance = {
            **proposal.provenance,
            "generator": "deterministic+ai",
            "provider": result.provider,
            "model": result.model,
            "prompt_key": result.prompt_key,
            "prompt_version": result.prompt_version,
        }

    # -- approve (the only write) ------------------------------------------------------------------

    def approve(self, profile_id: str, job_id: str, values: dict[str, Any], provenance: dict[str, Any]) -> ApplicationPackageModel:
        """Persist the reviewed proposal as the profile's package for the job."""
        values = {**values, "status": "APPROVED", "approved_at": datetime.now(UTC), "provenance_json": provenance}
        return self.resume.save_package(profile_id, job_id, values)


__all__ = ["ProfileService", "Proposal", "PreparationService"]
