from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerflow.api.schemas.jobs import (
    EvaluateRequest,
    JobCreate,
    JobEvaluationOutput,
    JobImport,
    JobOutput,
    JobRequirementCreate,
    JobRequirementOutput,
    JobSourceRecordCreate,
    JobSourceRecordOutput,
    JobUpdate,
    StatusHistoryOutput,
    WorkflowActionRequest,
    WorkflowStatusOutput,
)
from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobNotFoundError, JobService
from careerflow.application.jobs.workflow import JobWorkflowService
from careerflow.application.profiles.service import ProfileNotFoundError, ProfileService
from careerflow.domain.jobs.workflow import InvalidTransitionError, WorkflowStatus
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


def get_workflow_service(session: Session = Depends(get_session)) -> JobWorkflowService:
    return JobWorkflowService(session)


def not_found(error: Exception) -> HTTPException:
    kind = "profile" if isinstance(error, ProfileNotFoundError) else "job"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} not found")


@router.get("", response_model=list[JobOutput])
def list_jobs(job_service: JobService = Depends(get_job_service)) -> list[JobOutput]:
    return [JobOutput.model_validate(job) for job in job_service.list_jobs()]


@router.post("", response_model=JobOutput, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate, job_service: JobService = Depends(get_job_service)
) -> JobOutput:
    try:
        job = job_service.create_job(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job conflict") from error
    return JobOutput.model_validate(job)


@router.post("/import", response_model=JobOutput, status_code=status.HTTP_201_CREATED)
def import_job(
    payload: JobImport,
    job_service: JobService = Depends(get_job_service),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> JobOutput:
    """Manual or fixture import: description text is required, URL capture is optional.

    The new job is evaluated (deterministic rules only) against every existing profile.
    """
    job_values = payload.model_dump(exclude={"source", "requirements"})
    job_values["status"] = "READY_FOR_REVIEW"
    try:
        job = job_service.create_job(job_values)
        if payload.source is not None:
            job_service.add_source_record(job.id, payload.source.model_dump())
        for requirement in payload.requirements:
            job_service.add_requirement(job.id, requirement.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job conflict") from error
    evaluation_service.evaluate_job_for_all_profiles(job.id)
    return JobOutput.model_validate(job)


@router.get("/{job_id}", response_model=JobOutput)
def get_job(job_id: str, job_service: JobService = Depends(get_job_service)) -> JobOutput:
    try:
        return JobOutput.model_validate(job_service.get_job(job_id))
    except JobNotFoundError as error:
        raise not_found(error) from error


@router.patch("/{job_id}", response_model=JobOutput)
@router.put("/{job_id}", response_model=JobOutput)
def update_job(
    job_id: str, payload: JobUpdate, job_service: JobService = Depends(get_job_service)
) -> JobOutput:
    try:
        changes = payload.model_dump(exclude_unset=True)
        required = ("title", "company", "description_text", "raw_metadata_json")
        values = {k: v for k, v in changes.items() if v is not None or k not in required}
        job = job_service.update_job(job_id, values)
    except JobNotFoundError as error:
        raise not_found(error) from error
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job conflict") from error
    return JobOutput.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, job_service: JobService = Depends(get_job_service)) -> None:
    try:
        job_service.delete_job(job_id)
    except JobNotFoundError as error:
        raise not_found(error) from error


@router.get("/{job_id}/sources", response_model=list[JobSourceRecordOutput])
def list_source_records(
    job_id: str, service: JobService = Depends(get_job_service)
) -> list[JobSourceRecordOutput]:
    try:
        records = service.list_source_records(job_id)
    except JobNotFoundError as error:
        raise not_found(error) from error
    return [JobSourceRecordOutput.model_validate(r) for r in records]


@router.post(
    "/{job_id}/sources", response_model=JobSourceRecordOutput, status_code=status.HTTP_201_CREATED
)
def add_source_record(
    job_id: str, payload: JobSourceRecordCreate, service: JobService = Depends(get_job_service)
) -> JobSourceRecordOutput:
    try:
        record = service.add_source_record(job_id, payload.model_dump())
    except JobNotFoundError as error:
        raise not_found(error) from error
    return JobSourceRecordOutput.model_validate(record)


@router.get("/{job_id}/requirements", response_model=list[JobRequirementOutput])
def list_requirements(
    job_id: str, job_service: JobService = Depends(get_job_service)
) -> list[JobRequirementOutput]:
    try:
        requirements = job_service.list_requirements(job_id)
    except JobNotFoundError as error:
        raise not_found(error) from error
    return [JobRequirementOutput.model_validate(r) for r in requirements]


@router.post(
    "/{job_id}/requirements",
    response_model=JobRequirementOutput,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement(
    job_id: str, payload: JobRequirementCreate, job_service: JobService = Depends(get_job_service)
) -> JobRequirementOutput:
    try:
        requirement = job_service.add_requirement(job_id, payload.model_dump())
    except JobNotFoundError as error:
        raise not_found(error) from error
    return JobRequirementOutput.model_validate(requirement)


@router.get("/{job_id}/evaluations", response_model=list[JobEvaluationOutput])
def list_evaluations(
    job_id: str,
    profile_id: str | None = None,
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> list[JobEvaluationOutput]:
    """Evaluation history (newest first), optionally for one profile."""
    try:
        rows = evaluation_service.list_evaluations(job_id, profile_id)
    except JobNotFoundError as error:
        raise not_found(error) from error
    return [JobEvaluationOutput.model_validate(row) for row in rows]


@router.post(
    "/{job_id}/evaluations", response_model=JobEvaluationOutput, status_code=status.HTTP_201_CREATED
)
@router.post(
    "/{job_id}/evaluate", response_model=JobEvaluationOutput, status_code=status.HTTP_201_CREATED
)
def evaluate_job(
    job_id: str,
    payload: EvaluateRequest,
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> JobEvaluationOutput:
    """Run the deterministic evaluator; always appends a new evaluation row."""
    try:
        row = evaluation_service.evaluate_job_for_profile(job_id, payload.profile_id)
    except (JobNotFoundError, ProfileNotFoundError) as error:
        raise not_found(error) from error
    return JobEvaluationOutput.model_validate(row)


@router.post(
    "/{job_id}/evaluate-all",
    response_model=list[JobEvaluationOutput],
    status_code=status.HTTP_201_CREATED,
)
def evaluate_job_for_all_profiles(
    job_id: str, evaluation_service: EvaluationService = Depends(get_evaluation_service)
) -> list[JobEvaluationOutput]:
    """Re-evaluate the job for every profile; each run appends new history rows."""
    try:
        rows = evaluation_service.evaluate_job_for_all_profiles(job_id)
    except JobNotFoundError as error:
        raise not_found(error) from error
    return [JobEvaluationOutput.model_validate(row) for row in rows]


@router.get("/{job_id}/comparison", response_model=list[JobEvaluationOutput])
def compare_profiles(
    job_id: str, evaluation_service: EvaluationService = Depends(get_evaluation_service)
) -> list[JobEvaluationOutput]:
    """Latest evaluation of the job for each profile, for side-by-side comparison."""
    try:
        rows = evaluation_service.latest_per_profile(job_id)
    except JobNotFoundError as error:
        raise not_found(error) from error
    return [JobEvaluationOutput.model_validate(row) for row in rows]


@router.get("/{job_id}/evaluations/latest", response_model=JobEvaluationOutput | None)
def get_latest_evaluation(
    job_id: str,
    profile_id: str,
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> JobEvaluationOutput | None:
    try:
        row = evaluation_service.get_job_evaluation(job_id, profile_id)
    except (JobNotFoundError, ProfileNotFoundError) as error:
        raise not_found(error) from error
    return None if row is None else JobEvaluationOutput.model_validate(row)


# -- profile-scoped workflow -------------------------------------------------------------


def _apply(
    target: WorkflowStatus,
    job_id: str,
    payload: WorkflowActionRequest,
    workflow: JobWorkflowService,
) -> WorkflowStatusOutput:
    try:
        new = workflow.transition(payload.profile_id, job_id, target, payload.actor, payload.reason)
    except (JobNotFoundError, ProfileNotFoundError) as error:
        raise not_found(error) from error
    except InvalidTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return WorkflowStatusOutput(job_id=job_id, profile_id=payload.profile_id, status=new.value)


@router.post("/{job_id}/shortlist", response_model=WorkflowStatusOutput)
def shortlist_job(
    job_id: str,
    payload: WorkflowActionRequest,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusOutput:
    return _apply(WorkflowStatus.SHORTLISTED, job_id, payload, workflow)


@router.post("/{job_id}/reject", response_model=WorkflowStatusOutput)
def reject_job(
    job_id: str,
    payload: WorkflowActionRequest,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusOutput:
    return _apply(WorkflowStatus.REJECTED, job_id, payload, workflow)


@router.post("/{job_id}/save", response_model=WorkflowStatusOutput)
def save_job(
    job_id: str,
    payload: WorkflowActionRequest,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusOutput:
    return _apply(WorkflowStatus.SAVED, job_id, payload, workflow)


@router.post("/{job_id}/archive", response_model=WorkflowStatusOutput)
def archive_job(
    job_id: str,
    payload: WorkflowActionRequest,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusOutput:
    return _apply(WorkflowStatus.ARCHIVED, job_id, payload, workflow)


@router.get("/{job_id}/workflow", response_model=WorkflowStatusOutput)
def get_workflow_status(
    job_id: str,
    profile_id: str,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusOutput:
    try:
        current = workflow.get_status(profile_id, job_id)
    except (JobNotFoundError, ProfileNotFoundError) as error:
        raise not_found(error) from error
    return WorkflowStatusOutput(job_id=job_id, profile_id=profile_id, status=current.value)


@router.get("/{job_id}/status-history", response_model=list[StatusHistoryOutput])
def get_status_history(
    job_id: str,
    profile_id: str,
    workflow: JobWorkflowService = Depends(get_workflow_service),
) -> list[StatusHistoryOutput]:
    try:
        rows = workflow.history(profile_id, job_id)
    except (JobNotFoundError, ProfileNotFoundError) as error:
        raise not_found(error) from error
    return [StatusHistoryOutput.model_validate(row) for row in rows]
