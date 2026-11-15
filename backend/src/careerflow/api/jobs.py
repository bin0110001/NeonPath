from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobNotFoundError, JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.infrastructure.database.models import (
    JobModel,
)
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def get_job_service(session: Session = Depends(get_session)) -> JobService:
    return JobService(session)


def get_profile_service(session: Session = Depends(get_session)) -> ProfileService:
    return ProfileService(session)


def get_evaluation_service(
    job_service: JobService = Depends(get_job_service),
    profile_service: ProfileService = Depends(get_profile_service),
) -> EvaluationService:
    return EvaluationService(job_service, profile_service)


def require_job_service(service: JobService, job_id: str) -> JobModel:
    try:
        return service.get_job(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


@router.get("", response_model=list[dict[str, Any]])
def list_jobs(job_service: JobService = Depends(get_job_service)) -> list[dict[str, Any]]:
    jobs = job_service.list_jobs()
    return [
        {
            "id": job.id,
            "canonical_url": job.canonical_url,
            "title": job.title,
            "company": job.company,
            "company_domain": job.company_domain,
            "description_text": job.description_text,
            "description_html": job.description_html,
            "location_text": job.location_text,
            "remote_type": job.remote_type,
            "employment_type": job.employment_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "posted_at": job.posted_at,
            "expires_at": job.expires_at,
            "discovered_at": job.discovered_at,
            "source_updated_at": job.source_updated_at,
            "source_status": job.source_status,
            "fingerprint": job.fingerprint,
            "raw_metadata_json": job.raw_metadata_json,
        }
        for job in jobs
    ]


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_job(payload: dict[str, Any], job_service: JobService = Depends(get_job_service)) -> dict[str, Any]:
    try:
        job = job_service.create_job(payload)
        return {
            "id": job.id,
            "canonical_url": job.canonical_url,
            "title": job.title,
            "company": job.company,
            "company_domain": job.company_domain,
            "description_text": job.description_text,
            "description_html": job.description_html,
            "location_text": job.location_text,
            "remote_type": job.remote_type,
            "employment_type": job.employment_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "posted_at": job.posted_at,
            "expires_at": job.expires_at,
            "discovered_at": job.discovered_at,
            "source_updated_at": job.source_updated_at,
            "source_status": job.source_status,
            "fingerprint": job.fingerprint,
            "raw_metadata_json": job.raw_metadata_json,
        }
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job conflict") from error


@router.get("/{job_id}", response_model=dict[str, Any])
def get_job(job_id: str, job_service: JobService = Depends(get_job_service)) -> dict[str, Any]:
    job = require_job_service(job_service, job_id)
    return {
        "id": job.id,
        "canonical_url": job.canonical_url,
        "title": job.title,
        "company": job.company,
        "company_domain": job.company_domain,
        "description_text": job.description_text,
        "description_html": job.description_html,
        "location_text": job.location_text,
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "posted_at": job.posted_at,
        "expires_at": job.expires_at,
        "discovered_at": job.discovered_at,
        "source_updated_at": job.source_updated_at,
        "source_status": job.source_status,
        "fingerprint": job.fingerprint,
        "raw_metadata_json": job.raw_metadata_json,
    }


@router.put("/{job_id}", response_model=dict[str, Any])
def update_job(
    job_id: str, payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    try:
        job = job_service.update_job(job_id, payload)
        return {
            "id": job.id,
            "canonical_url": job.canonical_url,
            "title": job.title,
            "company": job.company,
            "company_domain": job.company_domain,
            "description_text": job.description_text,
            "description_html": job.description_html,
            "location_text": job.location_text,
            "remote_type": job.remote_type,
            "employment_type": job.employment_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "posted_at": job.posted_at,
            "expires_at": job.expires_at,
            "discovered_at": job.discovered_at,
            "source_updated_at": job.source_updated_at,
            "source_status": job.source_status,
            "fingerprint": job.fingerprint,
            "raw_metadata_json": job.raw_metadata_json,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job conflict") from error


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, job_service: JobService = Depends(get_job_service)) -> None:
    try:
        job_service.delete_job(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


# Source records endpoints
@router.get("/{job_id}/sources", response_model=list[dict[str, Any]])
def list_source_records(
    job_id: str, service: JobService = Depends(get_job_service)
) -> list[dict[str, Any]]:
    require_job_service(service, job_id)  # Validate job exists
    sources = service.list_source_records(job_id)
    return [
        {
            "id": source.id,
            "job_id": source.job_id,
            "adapter": source.adapter,
            "external_id": source.external_id,
            "source_url": source.source_url,
            "raw_payload": source.raw_payload,
            "discovered_at": source.discovered_at,
            "last_seen_at": source.last_seen_at,
        }
        for source in sources
    ]


@router.post("/{job_id}/sources", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def add_source_record(
    job_id: str, payload: dict[str, Any], service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    try:
        source = service.add_source_record(job_id, payload)
        return {
            "id": source.id,
            "job_id": source.job_id,
            "adapter": source.adapter,
            "external_id": source.external_id,
            "source_url": source.source_url,
            "raw_payload": source.raw_payload,
            "discovered_at": source.discovered_at,
            "last_seen_at": source.last_seen_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


# Requirements endpoints
@router.get("/{job_id}/requirements", response_model=list[dict[str, Any]])
def list_requirements(
    job_id: str, job_service: JobService = Depends(get_job_service)
) -> list[dict[str, Any]]:
    require_job_service(job_service, job_id)  # Validate job exists
    requirements = job_service.list_requirements(job_id)
    return [
        {
            "id": req.id,
            "job_id": req.job_id,
            "type": req.type,
            "normalized_text": req.normalized_text,
            "source_text": req.source_text,
            "required_level": req.required_level,
            "category": req.category,
            "confidence": req.confidence,
        }
        for req in requirements
    ]


@router.post("/{job_id}/requirements", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def add_requirement(
    job_id: str, payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    try:
        requirement = job_service.add_requirement(job_id, payload)
        return {
            "id": requirement.id,
            "job_id": requirement.job_id,
            "type": requirement.type,
            "normalized_text": requirement.normalized_text,
            "source_text": requirement.source_text,
            "required_level": requirement.required_level,
            "category": requirement.category,
            "confidence": requirement.confidence,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


# Evaluations endpoints
@router.get("/{job_id}/evaluations", response_model=list[dict[str, Any]])
def list_evaluations(
    job_id: str, evaluation_service: EvaluationService = Depends(get_evaluation_service)
) -> list[dict[str, Any]]:
    require_job_service(evaluation_service.job_service, job_id)  # Validate job exists
    evaluations = evaluation_service.job_service.list_evaluations(job_id)
    return [
        {
            "id": eval.id,
            "job_id": eval.job_id,
            "profile_id": eval.profile_id,
            "evaluator_version": eval.evaluator_version,
            "model_provider": eval.model_provider,
            "model_name": eval.model_name,
            "overall_score": eval.overall_score,
            "confidence": eval.confidence,
            "dimension_scores_json": eval.dimension_scores_json,
            "strengths": eval.strengths,
            "transferable_matches": eval.transferable_matches,
            "gaps": eval.gaps,
            "blockers": eval.blockers,
            "unknowns": eval.unknowns,
            "explanation": eval.explanation,
            "created_at": eval.created_at,
        }
        for eval in evaluations
    ]


@router.post("/{job_id}/evaluations", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def add_evaluation(
    job_id: str, payload: dict[str, Any], evaluation_service: EvaluationService = Depends(get_evaluation_service)
) -> dict[str, Any]:
    # For MVP, we'll require profile_id in the payload
    profile_id = payload.pop("profile_id", None)
    if not profile_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_id is required")
    
    try:
        evaluation = evaluation_service.evaluate_job_for_profile(
            job_id, profile_id, evaluation_service.job_service.session
        )
        return {
            "id": evaluation.id,
            "job_id": evaluation.job_id,
            "profile_id": evaluation.profile_id,
            "evaluator_version": evaluation.evaluator_version,
            "model_provider": evaluation.model_provider,
            "model_name": evaluation.model_name,
            "overall_score": evaluation.overall_score,
            "confidence": evaluation.confidence,
            "dimension_scores_json": evaluation.dimension_scores_json,
            "strengths": evaluation.strengths,
            "transferable_matches": evaluation.transferable_matches,
            "gaps": evaluation.gaps,
            "blockers": evaluation.blockers,
            "unknowns": evaluation.unknowns,
            "explanation": evaluation.explanation,
            "created_at": evaluation.created_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


@router.get("/{job_id}/evaluations/latest", response_model=dict[str, Any] | None)
def get_latest_evaluation(
    job_id: str, profile_id: str, evaluation_service: EvaluationService = Depends(get_evaluation_service)
) -> dict[str, Any] | None:
    try:
        evaluation = evaluation_service.get_job_evaluation(
            job_id, profile_id, evaluation_service.job_service.session
        )
        if evaluation is None:
            return None
        return {
            "id": evaluation.id,
            "job_id": evaluation.job_id,
            "profile_id": evaluation.profile_id,
            "evaluator_version": evaluation.evaluator_version,
            "model_provider": evaluation.model_provider,
            "model_name": evaluation.model_name,
            "overall_score": evaluation.overall_score,
            "confidence": evaluation.confidence,
            "dimension_scores_json": evaluation.dimension_scores_json,
            "strengths": evaluation.strengths,
            "transferable_matches": evaluation.transferable_matches,
            "gaps": evaluation.gaps,
            "blockers": evaluation.blockers,
            "unknowns": evaluation.unknowns,
            "explanation": evaluation.explanation,
            "created_at": evaluation.created_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


# Workflow action endpoints
@router.post("/{job_id}/shortlist", response_model=dict[str, Any])
def shortlist_job(
    job_id: str, payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    """Shortlist a job."""
    actor = payload.get("actor", "user")
    reason = payload.get("reason", "Job shortlisted")
    
    try:
        job = job_service.shortlist_job(job_id, actor, reason)
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "status": job.status,
            "discovered_at": job.discovered_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


@router.post("/{job_id}/reject", response_model=dict[str, Any])
def reject_job(
    job_id: str, payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    """Reject a job."""
    actor = payload.get("actor", "user")
    reason = payload.get("reason", "Job rejected")
    
    try:
        job = job_service.reject_job(job_id, actor, reason)
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "status": job.status,
            "discovered_at": job.discovered_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


@router.post("/{job_id}/save", response_model=dict[str, Any])
def save_job(
    job_id: str, payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    """Save a job."""
    actor = payload.get("actor", "user")
    reason = payload.get("reason", "Job saved")
    
    try:
        job = job_service.save_job(job_id, actor, reason)
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "status": job.status,
            "discovered_at": job.discovered_at,
        }
    except JobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error


# Demo/import endpoints
@router.post("/import", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def import_fixture_job(
    payload: dict[str, Any], job_service: JobService = Depends(get_job_service)
) -> dict[str, Any]:
    """
    Import a single job from fixture data.
    This is useful for demo purposes and testing.
    """
    try:
        # Extract job data from payload
        job_data = {
            "title": payload.get("title"),
            "company": payload.get("company"),
            "company_domain": payload.get("company_domain"),
            "description_text": payload.get("description_text"),
            "description_html": payload.get("description_html"),
            "location_text": payload.get("location_text"),
            "remote_type": payload.get("remote_type"),
            "employment_type": payload.get("employment_type"),
            "salary_min": payload.get("salary_min"),
            "salary_max": payload.get("salary_max"),
            "salary_currency": payload.get("salary_currency"),
            "salary_period": payload.get("salary_period"),
            "canonical_url": payload.get("canonical_url"),
        }
        
        # Remove None values
        job_data = {k: v for k, v in job_data.items() if v is not None}
        
        # Create the job
        job = job_service.create_job(job_data)
        
        # Add source record if provided
        if "source" in payload and payload["source"]:
            source_data = payload["source"]
            source_data["job_id"] = job.id
            job_service.add_source_record(job.id, source_data)
        
        # Add requirements if provided
        if "requirements" in payload and payload["requirements"]:
            for req_data in payload["requirements"]:
                req_data["job_id"] = job.id
                job_service.add_requirement(job.id, req_data)
        
        return {
            "id": job.id,
            "canonical_url": job.canonical_url,
            "title": job.title,
            "company": job.company,
            "company_domain": job.company_domain,
            "description_text": job.description_text,
            "description_html": job.description_html,
            "location_text": job.location_text,
            "remote_type": job.remote_type,
            "employment_type": job.employment_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "posted_at": job.posted_at,
            "expires_at": job.expires_at,
            "discovered_at": job.discovered_at,
            "source_updated_at": job.source_updated_at,
            "source_status": job.source_status,
            "fingerprint": job.fingerprint,
            "raw_metadata_json": job.raw_metadata_json,
        }
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error