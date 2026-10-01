"""
Application service for job evaluations.
Orchestrates deterministic evaluation of jobs against profiles.
"""

from typing import Optional
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.evaluations.service import DeterministicEvaluator, create_deterministic_evaluator
from careerflow.infrastructure.database.models import (
    JobModel,
    ProfileModel,
    JobEvaluationModel,
)


class EvaluationService:
    """Service for evaluating jobs against profiles using deterministic rules."""
    
    def __init__(
        self, 
        job_service: JobService,
        profile_service: ProfileService,
        evaluator: Optional[DeterministicEvaluator] = None
    ):
        self.job_service = job_service
        self.profile_service = profile_service
        self.evaluator = evaluator or create_deterministic_evaluator()
    
    def evaluate_job_for_profile(
        self, 
        job_id: str, 
        profile_id: str,
        session: Session
    ) -> JobEvaluationModel:
        """
        Evaluate a job against a profile and store the evaluation.
        
        Args:
            job_id: ID of the job to evaluate
            profile_id: ID of the profile to evaluate against
            session: Database session
            
        Returns:
            Created JobEvaluationModel
        """
        # Get job and profile
        job = self.job_service.get_job(job_id)
        profile = self.profile_service.get_profile(profile_id)
        
        # Get related data for evaluation
        role_families = self.profile_service.list_role_families(profile_id)
        role_targets = self.profile_service.list_role_targets(profile_id)
        search_prefs = self.profile_service.get_search_preferences(profile_id)
        scoring_prefs = self.profile_service.get_scoring_preferences(profile_id)
        
        # Convert ORM models to domain models for evaluation
        # For now, we'll work with the ORM models directly since they have the needed fields
        # In a more complex implementation, we might convert to domain models
        
        # Perform deterministic evaluation
        evaluation_result = self.evaluator.evaluate_job_against_profile(
            job=job,
            profile=profile,
            role_families=role_families,
            role_targets=role_targets,
            search_prefs=search_prefs,
            scoring_prefs=scoring_prefs
        )
        
        # Create evaluation record
        evaluation_data = {
            "job_id": job_id,
            "profile_id": profile_id,
            "evaluator_version": evaluation_result["evaluator_version"],
            "model_provider": evaluation_result["model_provider"],
            "model_name": evaluation_result["model_name"],
            "overall_score": evaluation_result["overall_score"],
            "confidence": evaluation_result["confidence"],
            "dimension_scores_json": evaluation_result["dimension_scores_json"],
            "strengths": evaluation_result["strengths"],
            "transferable_matches": evaluation_result["transferable_matches"],
            "gaps": evaluation_result["gaps"],
            "blockers": evaluation_result["blockers"],
            "unknowns": evaluation_result["unknowns"],
            "explanation": evaluation_result["explanation"],
        }
        
        evaluation = JobEvaluationModel(**evaluation_data)
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)
        
        return evaluation
    
    def get_job_evaluation(
        self, 
        job_id: str, 
        profile_id: str,
        session: Session
    ) -> Optional[JobEvaluationModel]:
        """Get the latest evaluation for a job-profile pair."""
        # Validate job and profile exist
        self.job_service.get_job(job_id)
        self.profile_service.get_profile(profile_id)
        
        # Get latest evaluation
        from sqlalchemy import select
        statement = select(JobEvaluationModel).where(
            JobEvaluationModel.job_id == job_id,
            JobEvaluationModel.profile_id == profile_id
        ).order_by(JobEvaluationModel.created_at.desc())
        
        return session.scalars(statement).first()
    
    def reevaluate_job_for_profile(
        self, 
        job_id: str, 
        profile_id: str,
        session: Session
    ) -> JobEvaluationModel:
        """
        Re-evaluate a job against a profile (creates new evaluation record).
        
        Args:
            job_id: ID of the job to reevaluate
            profile_id: ID of the profile to evaluate against
            session: Database session
            
        Returns:
            New JobEvaluationModel
        """
        # Simply call evaluate_job_for_profile which will create a new record
        return self.evaluate_job_for_profile(job_id, profile_id, session)


# Factory function for dependency injection
def create_evaluation_service(
    job_service: JobService,
    profile_service: ProfileService,
    evaluator: Optional[DeterministicEvaluator] = None
) -> EvaluationService:
    """Create an evaluation service instance."""
    return EvaluationService(job_service, profile_service, evaluator)