"""Interview preparation: deterministic core plus optional, evidence-validated AI additions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from careerflow.application.ai.client import AiClient
from careerflow.application.applications.prepare import PreparationService
from careerflow.application.evaluations.mappers import load_skill_catalog
from careerflow.application.evaluations.semantic import collect_evidence
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.ai.ports import AiError, AiUnavailableError
from careerflow.domain.applications.interview_prep import PREP_VERSION, prepare
from careerflow.domain.applications.tailoring import JobFacts
from careerflow.domain.evaluations.semantic import Claim, validate_claims
from careerflow.infrastructure.database.models import (
    ApplicationModel,
    InterviewModel,
    JobModel,
)

PROMPT_KEY = "interview_prep"


class StoryOut(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(default_factory=list)


class InterviewPrepOut(BaseModel):
    focus_areas: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    story_suggestions: list[StoryOut] = Field(default_factory=list)


class InterviewPrepService:
    def __init__(self, session: Session, ai: AiClient | None = None) -> None:
        self.session = session
        self.ai = ai
        self.profiles = ProfileService(session)

    def prepare(self, profile_id: str, interview_id: str) -> dict[str, Any]:
        """Generate preparation for the interview and store it on the interview record."""
        interview = self.profiles.get_profile_item(InterviewModel, profile_id, interview_id)
        application = self.profiles.get_profile_item(ApplicationModel, profile_id, interview.application_id)
        job = self.session.get(JobModel, application.job_id)
        assert job is not None
        skills, achievements, _ = PreparationService(self.session)._facts(profile_id)
        required = tuple(r.normalized_text for r in job.requirements if r.type == "skill" and (r.required_level or "REQUIRED") == "REQUIRED")
        preferred = tuple(r.normalized_text for r in job.requirements if r.type == "skill" and r.required_level == "PREFERRED")
        catalog = [s.name for s in load_skill_catalog(self.session)]
        result = prepare(interview.type, JobFacts(job.title, job.description_text, required, preferred), job.company, skills, achievements, catalog)

        data: dict[str, Any] = asdict(result)
        data["ai_stories"] = []
        data["ai_note"] = None
        data["provenance"] = {"generator": "deterministic", "version": PREP_VERSION}
        self._augment(data, job, interview.type, profile_id)
        interview.prep_json = data
        self.session.commit()
        return data

    def _augment(self, data: dict[str, Any], job: JobModel, interview_type: str, profile_id: str) -> None:
        if self.ai is None:
            data["ai_note"] = "AI is not configured: deterministic preparation only."
            return
        evidence = collect_evidence(self.session, profile_id)
        try:
            result = self.ai.run(
                PROMPT_KEY,
                {
                    "title": job.title,
                    "company": job.company,
                    "interview_type": interview_type,
                    "description": job.description_text,
                    "evidence": "\n".join(f"{i}: {t}" for i, t in evidence.items()) or "(none)",
                },
                InterviewPrepOut,
            )
        except AiUnavailableError:
            data["ai_note"] = "AI is disabled: deterministic preparation only."
            return
        except AiError as error:
            data["ai_note"] = f"AI drafting failed ({type(error).__name__}): deterministic preparation only."
            return
        for item in result.value.focus_areas:
            if item not in data["focus_areas"]:
                data["focus_areas"].append(item)
        for question in result.value.questions_to_ask:
            if question not in data["questions_to_ask"]:
                data["questions_to_ask"].append(question)
        checked = validate_claims(
            [Claim(s.text, "strength", "evidence", tuple(s.evidence_ids)) for s in result.value.story_suggestions],
            set(evidence),
        )
        data["ai_stories"] = [
            {"text": c.text, "basis": c.basis, "evidence_ids": list(c.evidence_ids), "note": c.note} for c in checked
        ]
        data["provenance"] = {
            "generator": "deterministic+ai", "version": PREP_VERSION, "provider": result.provider,
            "model": result.model, "prompt_version": result.prompt_version,
        }  # fmt: skip
