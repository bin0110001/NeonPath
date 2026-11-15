"""Semantic (AI) evaluation merged onto the deterministic one, with evidence validation."""

from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field
from sqlalchemy import select

from careerflow.application.ai.client import AiClient
from careerflow.application.evaluations.mappers import (
    load_skill_catalog,
    to_domain_job,
    to_domain_profile,
)
from careerflow.application.evaluations.service import EvaluationService
from careerflow.domain.ai.ports import AiUnavailableError
from careerflow.domain.evaluations.semantic import (
    Claim,
    SemanticFindings,
    merge_semantic,
    validate_claims,
)
from careerflow.domain.evaluations.service import EVALUATOR_VERSION
from careerflow.infrastructure.database.models import (
    AchievementModel,
    EducationModel,
    ExperienceModel,
    JobEvaluationModel,
    PortfolioItemModel,
    ProfileSkillModel,
    SkillModel,
)

PROMPT_KEY = "semantic_evaluation"
SEMANTIC_VERSION_TAG = "hybrid-v1"


class ClaimOut(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    kind: str = Field(pattern="^(strength|transferable|gap)$")
    basis: str = Field(pattern="^(evidence|inference|unverified)$")
    evidence_ids: list[str] = Field(default_factory=list)


class SemanticEvaluationOut(BaseModel):
    claims: list[ClaimOut] = Field(default_factory=list)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""


class SemanticEvaluationService:
    def __init__(self, base: EvaluationService, ai: AiClient) -> None:
        self.base = base
        self.ai = ai

    def evidence(self, profile_id: str) -> dict[str, str]:
        """Real profile records the model may cite: id -> one-line summary."""
        session = self.base.session
        found: dict[str, str] = {}
        for e in session.scalars(select(ExperienceModel).where(ExperienceModel.profile_id == profile_id)):
            found[f"experience:{e.id}"] = f"{e.title} at {e.organization}. {e.description or ''}".strip()
        for a in session.scalars(select(AchievementModel).where(AchievementModel.profile_id == profile_id)):
            detail = " ".join(filter(None, [a.situation, a.action, a.result]))
            found[f"achievement:{a.id}"] = f"{a.title}. {detail} {', '.join(a.technologies or [])}".strip()
        rows = session.execute(
            select(ProfileSkillModel, SkillModel)
            .join(SkillModel, SkillModel.id == ProfileSkillModel.skill_id)
            .where(ProfileSkillModel.profile_id == profile_id)
        )
        for link, skill in rows:
            years = f", {link.years_experience:g} years" if link.years_experience else ""
            found[f"skill:{skill.id}"] = f"{skill.canonical_name} ({skill.category or 'skill'}{years})"
        for ed in session.scalars(select(EducationModel).where(EducationModel.profile_id == profile_id)):
            found[f"education:{ed.id}"] = f"{ed.degree or ''} {ed.field_of_study or ''} {ed.institution}".strip()
        for p in session.scalars(select(PortfolioItemModel).where(PortfolioItemModel.profile_id == profile_id)):
            found[f"portfolio:{p.id}"] = f"{p.name}. {p.description or ''}".strip()
        return found

    def evaluate(self, job_id: str, profile_id: str) -> JobEvaluationModel:
        """Deterministic + semantic evaluation. If AI is unavailable the plain deterministic
        evaluation is stored and returned unchanged."""
        base = self.base
        job = base.job_service.get_job(job_id)
        profile = base.profile_service.get_profile(profile_id)
        evidence = self.evidence(profile_id)
        requirements = "\n".join(f"- {r.normalized_text} ({r.required_level or r.type})" for r in job.requirements)
        try:
            result = self.ai.run(
                PROMPT_KEY,
                {
                    "title": job.title,
                    "company": job.company,
                    "description": job.description_text,
                    "requirements": requirements or "(none extracted)",
                    "evidence": "\n".join(f"{i}: {text}" for i, text in evidence.items()) or "(none)",
                },
                SemanticEvaluationOut,
            )
        except AiUnavailableError:
            return base.evaluate_job_for_profile(job_id, profile_id)

        catalog = load_skill_catalog(base.session)
        domain_profile = to_domain_profile(base.session, profile, catalog)
        deterministic = base.evaluator.evaluate(to_domain_job(job), domain_profile, catalog)
        claims = validate_claims(
            [Claim(c.text, c.kind, c.basis, tuple(c.evidence_ids)) for c in result.value.claims],
            set(evidence),
        )
        merged = merge_semantic(
            deterministic,
            SemanticFindings(claims, result.value.dimension_scores, result.value.explanation),
            domain_profile,
            base.evaluator,
            version=f"{SEMANTIC_VERSION_TAG}+{EVALUATOR_VERSION}",
        )
        row = base.store(
            job_id,
            profile_id,
            merged,
            provider=result.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            claims=[asdict(c) | {"evidence_ids": list(c.evidence_ids)} for c in claims],
        )
        return row
