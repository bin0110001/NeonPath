"""Requirement extraction: AI when available, deterministic keywords otherwise."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from careerflow.application.ai.client import AiClient
from careerflow.application.ai.schemas import ExtractedItem, ExtractedRequirements
from careerflow.application.evaluations.mappers import load_skill_catalog
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.domain.ai.ports import AiUnavailableError
from careerflow.domain.jobs.keyword_extraction import KeywordItem, extract_keywords
from careerflow.infrastructure.database.models import JobModel, JobRequirementModel

PROMPT_KEY = "extract_requirements"
UNVERIFIED_QUOTE_CONFIDENCE = 0.3
EXTRACTED_BY = ("ai", "keyword")

# (ExtractedRequirements field, requirement type, level, category)
FIELD_MAP: tuple[tuple[str, str, str | None, str], ...] = (
    ("required_skills", "skill", "REQUIRED", "skill"),
    ("preferred_skills", "skill", "PREFERRED", "skill"),
    ("experience_requirements", "experience", "REQUIRED", "experience"),
    ("education_requirements", "education", "REQUIRED", "education"),
    ("leadership_expectations", "expectation", None, "leadership"),
    ("architecture_expectations", "expectation", None, "architecture"),
    ("management_expectations", "expectation", None, "management"),
    ("location_constraints", "constraint", None, "location"),
    ("travel_requirements", "constraint", None, "travel"),
    ("potential_blockers", "blocker", None, "other"),
    ("responsibilities", "responsibility", None, "other"),
    ("ambiguous_requirements", "ambiguous", None, "other"),
)


@dataclass
class ExtractionOutcome:
    mode: str  # "ai" or "keyword"
    requirements: list[JobRequirementModel]
    summary: str = ""
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#. ]+", " ", text.lower()).split())


def quote_is_grounded(quote: str, description: str) -> bool:
    return bool(quote.strip()) and _norm(quote) in _norm(description)


class RequirementExtractionService:
    def __init__(self, session: Session, ai: AiClient | None = None) -> None:
        self.session = session
        self.ai = ai

    def extract(self, job_id: str) -> ExtractionOutcome:
        """(Re)extract requirements. Manually entered rows are kept; earlier extracted rows
        are replaced because they are derived data that the new run supersedes."""
        job = self.session.get(JobModel, job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        outcome = self._run(job)  # may raise AiError: nothing is persisted then
        self.session.execute(
            delete(JobRequirementModel).where(
                JobRequirementModel.job_id == job_id,
                JobRequirementModel.extractor.in_(EXTRACTED_BY),
            )
        )
        self.session.add_all(outcome.requirements)
        self.session.commit()
        return outcome

    def _run(self, job: JobModel) -> ExtractionOutcome:
        if self.ai is None:
            return self._keywords(job, reason="AI is not configured")
        try:
            result = self.ai.run(
                PROMPT_KEY,
                {"title": job.title, "company": job.company, "description": job.description_text},
                ExtractedRequirements,
            )
        except AiUnavailableError as error:
            return self._keywords(job, reason=str(error))
        rows = self._ai_rows(job, result.value)
        for row in rows:
            row.provider = result.provider
            row.model_name = result.model
            row.prompt_version = result.prompt_version
        return ExtractionOutcome(
            "ai", rows, result.value.summary, result.provider, result.model, result.prompt_version
        )

    def _ai_rows(self, job: JobModel, data: ExtractedRequirements) -> list[JobRequirementModel]:
        rows: list[JobRequirementModel] = []
        for field_name, rtype, level, category in FIELD_MAP:
            for item in getattr(data, field_name):
                rows.append(self._row(job, item, rtype, level, category))
        if data.inferred_seniority:
            seniority = ExtractedItem(text=data.inferred_seniority, source_quote="", confidence=0.6)
            rows.append(self._row(job, seniority, "seniority", None, "other"))
        return rows

    @staticmethod
    def _row(
        job: JobModel, item: ExtractedItem, rtype: str, level: str | None, category: str
    ) -> JobRequirementModel:
        confidence = item.confidence
        if item.source_quote and not quote_is_grounded(item.source_quote, job.description_text):
            confidence = min(confidence, UNVERIFIED_QUOTE_CONFIDENCE)  # quote not in the text
        return JobRequirementModel(
            job_id=job.id,
            type=rtype,
            normalized_text=item.text[:200],
            source_text=item.source_quote or item.text,
            required_level=level,
            category=category,
            confidence=confidence,
            extractor="ai",
        )

    def _keywords(self, job: JobModel, reason: str) -> ExtractionOutcome:
        found = extract_keywords(job.title, job.description_text, load_skill_catalog(self.session))
        rows: list[JobRequirementModel] = []

        def add(items: list[KeywordItem], rtype: str, level: str | None, category: str) -> None:
            for item in items:
                rows.append(
                    JobRequirementModel(
                        job_id=job.id,
                        type=rtype,
                        normalized_text=item.text[:200],
                        source_text=item.source_quote,
                        required_level=level,
                        category=category,
                        confidence=item.confidence,
                        extractor="keyword",
                    )
                )

        add(found.required_skills, "skill", "REQUIRED", "skill")
        add(found.preferred_skills, "skill", "PREFERRED", "skill")
        add(found.architecture, "expectation", None, "architecture")
        add(found.leadership, "expectation", None, "leadership")
        add(found.management, "expectation", None, "management")
        add(found.travel, "constraint", None, "travel")
        if found.inferred_seniority:
            add([KeywordItem(found.inferred_seniority, job.title, 0.5)], "seniority", None, "other")
        return ExtractionOutcome("keyword", rows, fallback_reason=reason)

    def list_for_job(self, job_id: str) -> list[JobRequirementModel]:
        return list(
            self.session.scalars(select(JobRequirementModel).where(JobRequirementModel.job_id == job_id))
        )
