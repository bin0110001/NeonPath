"""Application service for job evaluations.

Orchestrates deterministic evaluation of one job against one profile. Evaluations are
append-only: every run adds a versioned row and earlier rows are never overwritten.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.evaluations.mappers import (
    load_skill_catalog,
    to_domain_job,
    to_domain_profile,
)
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.evaluations.service import (
    DeterministicEvaluator,
    EvaluationResult,
    create_deterministic_evaluator,
)
from careerflow.infrastructure.database.models import JobEvaluationModel, ProfileModel


class EvaluationService:
    def __init__(
        self,
        job_service: JobService,
        profile_service: ProfileService,
        evaluator: DeterministicEvaluator | None = None,
    ) -> None:
        self.job_service = job_service
        self.profile_service = profile_service
        self.evaluator = evaluator or create_deterministic_evaluator()

    @property
    def session(self) -> Session:
        return self.job_service.session

    def evaluate_job_for_profile(self, job_id: str, profile_id: str) -> JobEvaluationModel:
        """Evaluate and store a new evaluation row (also used for re-evaluation)."""
        job = self.job_service.get_job(job_id)
        profile = self.profile_service.get_profile(profile_id)
        catalog = load_skill_catalog(self.session)
        result = self.evaluator.evaluate(
            to_domain_job(job), to_domain_profile(self.session, profile, catalog), catalog
        )
        return self.store(job_id, profile_id, result)

    def store(
        self,
        job_id: str,
        profile_id: str,
        result: EvaluationResult,
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        claims: list[dict[str, Any]] | None = None,
    ) -> JobEvaluationModel:
        """Append a new evaluation row (history is never overwritten)."""
        evaluation = JobEvaluationModel(
            job_id=job_id,
            profile_id=profile_id,
            evaluator_version=result.evaluator_version,
            model_provider=provider or result.model_provider,
            model_name=model or result.model_name,
            prompt_version=prompt_version,
            claims_json=claims or [],
            overall_score=result.overall_score,
            confidence=result.confidence,
            dimension_scores_json=result.dimension_scores,
            strengths=result.strengths,
            transferable_matches=result.transferable_matches,
            gaps=result.gaps,
            blockers=result.blockers,
            unknowns=result.unknowns,
            explanation=result.explanation,
            created_at=datetime.now(UTC),  # microsecond precision keeps 'latest' unambiguous
        )
        self.session.add(evaluation)
        self.session.commit()
        self.session.refresh(evaluation)
        return evaluation

    def get_job_evaluation(self, job_id: str, profile_id: str) -> JobEvaluationModel | None:
        """Latest evaluation for a job-profile pair."""
        self.job_service.get_job(job_id)
        self.profile_service.get_profile(profile_id)
        statement = (
            select(JobEvaluationModel)
            .where(
                JobEvaluationModel.job_id == job_id,
                JobEvaluationModel.profile_id == profile_id,
            )
            .order_by(JobEvaluationModel.created_at.desc(), JobEvaluationModel.id)
        )
        return self.session.scalars(statement).first()

    def list_evaluations(
        self, job_id: str, profile_id: str | None = None
    ) -> list[JobEvaluationModel]:
        return self.job_service.list_evaluations(job_id, profile_id)

    def evaluate_job_for_all_profiles(self, job_id: str) -> list[JobEvaluationModel]:
        """Append one new evaluation per existing profile (deterministic only)."""
        self.job_service.get_job(job_id)
        profile_ids = list(self.session.scalars(select(ProfileModel.id).order_by(ProfileModel.slug)))
        return [self.evaluate_job_for_profile(job_id, profile_id) for profile_id in profile_ids]

    def latest_per_profile(self, job_id: str) -> list[JobEvaluationModel]:
        """The newest evaluation of the job for each profile that has one."""
        self.job_service.get_job(job_id)
        rows = self.session.scalars(
            select(JobEvaluationModel)
            .where(JobEvaluationModel.job_id == job_id)
            .order_by(JobEvaluationModel.created_at.desc(), JobEvaluationModel.id)
        )
        latest: dict[str, JobEvaluationModel] = {}
        for row in rows:
            latest.setdefault(row.profile_id, row)
        return list(latest.values())
