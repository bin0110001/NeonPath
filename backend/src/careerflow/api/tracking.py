from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.application.ai.config import build_client
from careerflow.application.applications.interview_service import InterviewPrepService
from careerflow.application.applications.resume import ResumeLinkError
from careerflow.application.applications.tracking import Card, TrackingError, TrackingService
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileNotFoundError
from careerflow.domain.jobs.workflow import InvalidTransitionError
from careerflow.infrastructure.database.models import ContactModel, FollowUpModel, InterviewModel
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(tags=["tracking"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def get_tracking(session: Session = Depends(get_session)) -> TrackingService:
    return TrackingService(session)


# -- schemas ---------------------------------------------------------------------------------


class ApplicationInput(BaseModel):
    job_id: str
    source: str | None = Field(default=None, max_length=100)
    applied_at: datetime | None = None
    resume_variant_id: str | None = None
    resume_artifact_id: str | None = None
    cover_letter_artifact_id: str | None = None
    compensation_entered: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class ApplicationOutput(ApplicationInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    created_at: datetime


class ContactInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    profile_url: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class ContactOutput(ContactInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str


class LinkContact(BaseModel):
    contact_id: str
    role: str = "other"


class LinkOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application_id: str
    contact_id: str
    role: str


class FollowUpInput(BaseModel):
    application_id: str
    due_at: datetime
    type: str = Field(default="check_in", max_length=50)
    notes: str | None = None


class FollowUpUpdate(BaseModel):
    due_at: datetime | None = None
    type: str | None = Field(default=None, max_length=50)
    notes: str | None = None


class FollowUpOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    application_id: str
    due_at: datetime
    type: str
    status: str
    notes: str | None
    completed_at: datetime | None


class InterviewInput(BaseModel):
    application_id: str
    type: str = "other"
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    participants: list[str] = Field(default_factory=list)
    meeting_url: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    outcome: str = "PENDING"
    post_notes: str | None = None
    next_steps: str | None = None


class InterviewOutput(InterviewInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    prep_json: dict[str, Any] = Field(default_factory=dict)


class CardOutput(BaseModel):
    job_id: str
    title: str
    company: str
    status: str
    score: float | None
    application_id: str | None
    applied_at: datetime | None
    next_follow_up_at: datetime | None
    next_interview_at: datetime | None


class PipelineOutput(BaseModel):
    columns: dict[str, list[CardOutput]]


class MetricsOutput(BaseModel):
    jobs_reviewed: int
    shortlisted: int
    applications_submitted: int
    screens: int
    interviews: int
    final_interviews: int
    offers: int
    responded: int
    response_rate: float | None
    median_days_to_response: float | None
    average_days_to_response: float | None


class OverviewOutput(BaseModel):
    due_follow_ups: list[FollowUpOutput]
    upcoming_interviews: list[InterviewOutput]
    metrics: MetricsOutput


class TransitionInput(BaseModel):
    profile_id: str
    to_status: str
    actor: str | None = Field(default=None, max_length=100)
    reason: str | None = None


class TransitionOutput(BaseModel):
    job_id: str
    profile_id: str
    status: str


# -- helpers ---------------------------------------------------------------------------------

_MISSING = (ProfileNotFoundError, ProfileItemNotFoundError, JobNotFoundError)


def _fail(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if isinstance(error, JobNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if isinstance(error, ProfileItemNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="record not found")
    if isinstance(error, InvalidTransitionError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


_ERRORS = (*_MISSING, TrackingError, ResumeLinkError, InvalidTransitionError)


def _card(card: Card) -> CardOutput:
    return CardOutput(**vars(card))


# -- applications -----------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/applications", response_model=list[ApplicationOutput])
def list_applications(profile_id: str, svc: TrackingService = Depends(get_tracking)) -> list[ApplicationOutput]:
    try:
        return [ApplicationOutput.model_validate(a) for a in svc.list_applications(profile_id)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/applications", response_model=ApplicationOutput, status_code=201)
def create_application(
    profile_id: str, payload: ApplicationInput, svc: TrackingService = Depends(get_tracking)
) -> ApplicationOutput:
    try:
        return ApplicationOutput.model_validate(svc.create_application(profile_id, payload.model_dump()))
    except TrackingError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/applications/{application_id}", response_model=ApplicationOutput)
def get_application(profile_id: str, application_id: str, svc: TrackingService = Depends(get_tracking)) -> ApplicationOutput:
    try:
        return ApplicationOutput.model_validate(svc.get_application(profile_id, application_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.put("/profiles/{profile_id}/applications/{application_id}", response_model=ApplicationOutput)
def update_application(
    profile_id: str, application_id: str, payload: ApplicationInput, svc: TrackingService = Depends(get_tracking)
) -> ApplicationOutput:
    try:
        row = svc.update_application(profile_id, application_id, payload.model_dump())
    except _ERRORS as error:
        raise _fail(error) from error
    return ApplicationOutput.model_validate(row)


@router.delete("/profiles/{profile_id}/applications/{application_id}", status_code=204)
def delete_application(profile_id: str, application_id: str, svc: TrackingService = Depends(get_tracking)) -> None:
    try:
        svc.delete_application(profile_id, application_id)
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/applications/{application_id}/contacts", response_model=list[LinkOutput])
def list_application_contacts(profile_id: str, application_id: str, svc: TrackingService = Depends(get_tracking)) -> list[LinkOutput]:
    try:
        return [LinkOutput.model_validate(link) for link in svc.application_contacts(profile_id, application_id)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/applications/{application_id}/contacts", response_model=LinkOutput, status_code=201)
def link_contact(
    profile_id: str, application_id: str, payload: LinkContact, svc: TrackingService = Depends(get_tracking)
) -> LinkOutput:
    try:
        return LinkOutput.model_validate(svc.link_contact(profile_id, application_id, payload.contact_id, payload.role))
    except _ERRORS as error:
        raise _fail(error) from error


@router.delete("/profiles/{profile_id}/applications/{application_id}/contacts/{contact_id}", status_code=204)
def unlink_contact(profile_id: str, application_id: str, contact_id: str, svc: TrackingService = Depends(get_tracking)) -> None:
    try:
        svc.unlink_contact(profile_id, application_id, contact_id)
    except _ERRORS as error:
        raise _fail(error) from error


# -- contacts ---------------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/contacts", response_model=list[ContactOutput])
def list_contacts(profile_id: str, svc: TrackingService = Depends(get_tracking)) -> list[ContactOutput]:
    try:
        return [ContactOutput.model_validate(c) for c in svc.profiles.list_profile_items(ContactModel, profile_id)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/contacts", response_model=ContactOutput, status_code=201)
def create_contact(profile_id: str, payload: ContactInput, svc: TrackingService = Depends(get_tracking)) -> ContactOutput:
    try:
        return ContactOutput.model_validate(svc.profiles.add_profile_item(ContactModel, profile_id, payload.model_dump()))
    except _ERRORS as error:
        raise _fail(error) from error


@router.put("/profiles/{profile_id}/contacts/{contact_id}", response_model=ContactOutput)
def update_contact(profile_id: str, contact_id: str, payload: ContactInput, svc: TrackingService = Depends(get_tracking)) -> ContactOutput:
    try:
        row = svc.profiles.update_profile_item(ContactModel, profile_id, contact_id, payload.model_dump())
    except _ERRORS as error:
        raise _fail(error) from error
    return ContactOutput.model_validate(row)


@router.delete("/profiles/{profile_id}/contacts/{contact_id}", status_code=204)
def delete_contact(profile_id: str, contact_id: str, svc: TrackingService = Depends(get_tracking)) -> None:
    try:
        svc.delete_contact(profile_id, contact_id)
    except _ERRORS as error:
        raise _fail(error) from error


# -- follow-ups ---------------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/follow-ups", response_model=list[FollowUpOutput])
def list_follow_ups(
    profile_id: str,
    status_: Annotated[str | None, Query(alias="status")] = None,
    due_by: datetime | None = None,
    svc: TrackingService = Depends(get_tracking),
) -> list[FollowUpOutput]:
    try:
        return [FollowUpOutput.model_validate(f) for f in svc.follow_ups(profile_id, status_, due_by)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/follow-ups", response_model=FollowUpOutput, status_code=201)
def create_follow_up(profile_id: str, payload: FollowUpInput, svc: TrackingService = Depends(get_tracking)) -> FollowUpOutput:
    try:
        return FollowUpOutput.model_validate(svc.create_follow_up(profile_id, payload.model_dump()))
    except _ERRORS as error:
        raise _fail(error) from error


@router.put("/profiles/{profile_id}/follow-ups/{follow_up_id}", response_model=FollowUpOutput)
def update_follow_up(
    profile_id: str, follow_up_id: str, payload: FollowUpUpdate, svc: TrackingService = Depends(get_tracking)
) -> FollowUpOutput:
    try:
        row = svc.profiles.update_profile_item(
            FollowUpModel, profile_id, follow_up_id, payload.model_dump(exclude_unset=True, exclude_none=True)
        )
    except _ERRORS as error:
        raise _fail(error) from error
    return FollowUpOutput.model_validate(row)


@router.post("/profiles/{profile_id}/follow-ups/{follow_up_id}/{action}", response_model=FollowUpOutput)
def resolve_follow_up(profile_id: str, follow_up_id: str, action: str, svc: TrackingService = Depends(get_tracking)) -> FollowUpOutput:
    target = {"complete": "DONE", "dismiss": "DISMISSED", "reopen": "OPEN"}.get(action)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown action")
    try:
        return FollowUpOutput.model_validate(svc.set_follow_up_status(profile_id, follow_up_id, target))
    except _ERRORS as error:
        raise _fail(error) from error


@router.delete("/profiles/{profile_id}/follow-ups/{follow_up_id}", status_code=204)
def delete_follow_up(profile_id: str, follow_up_id: str, svc: TrackingService = Depends(get_tracking)) -> None:
    try:
        svc.profiles.delete_profile_item(FollowUpModel, profile_id, follow_up_id)
    except _ERRORS as error:
        raise _fail(error) from error


# -- interviews ----------------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/interviews", response_model=list[InterviewOutput])
def list_interviews(profile_id: str, upcoming: bool = False, svc: TrackingService = Depends(get_tracking)) -> list[InterviewOutput]:
    try:
        return [InterviewOutput.model_validate(i) for i in svc.interviews(profile_id, upcoming_only=upcoming)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/interviews", response_model=InterviewOutput, status_code=201)
def create_interview(profile_id: str, payload: InterviewInput, svc: TrackingService = Depends(get_tracking)) -> InterviewOutput:
    try:
        return InterviewOutput.model_validate(svc.create_interview(profile_id, payload.model_dump()))
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/interviews/{interview_id}", response_model=InterviewOutput)
def get_interview(profile_id: str, interview_id: str, svc: TrackingService = Depends(get_tracking)) -> InterviewOutput:
    try:
        return InterviewOutput.model_validate(svc.profiles.get_profile_item(InterviewModel, profile_id, interview_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.put("/profiles/{profile_id}/interviews/{interview_id}", response_model=InterviewOutput)
def update_interview(
    profile_id: str, interview_id: str, payload: InterviewInput, svc: TrackingService = Depends(get_tracking)
) -> InterviewOutput:
    try:
        row = svc.update_interview(profile_id, interview_id, payload.model_dump())
    except _ERRORS as error:
        raise _fail(error) from error
    return InterviewOutput.model_validate(row)


@router.post("/profiles/{profile_id}/interviews/{interview_id}/prepare", response_model=dict[str, Any])
def prepare_interview(profile_id: str, interview_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Generate (and store on the interview) job-specific preparation grounded in the profile."""
    try:
        return InterviewPrepService(session, build_client(session)).prepare(profile_id, interview_id)
    except _ERRORS as error:
        raise _fail(error) from error


@router.delete("/profiles/{profile_id}/interviews/{interview_id}", status_code=204)
def delete_interview(profile_id: str, interview_id: str, svc: TrackingService = Depends(get_tracking)) -> None:
    try:
        svc.profiles.delete_profile_item(InterviewModel, profile_id, interview_id)
    except _ERRORS as error:
        raise _fail(error) from error


# -- pipeline, overview, transitions ---------------------------------------------------------------


@router.get("/profiles/{profile_id}/pipeline", response_model=PipelineOutput)
def pipeline(profile_id: str, svc: TrackingService = Depends(get_tracking)) -> PipelineOutput:
    try:
        return PipelineOutput(columns={k: [_card(c) for c in v] for k, v in svc.pipeline(profile_id).items()})
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/overview", response_model=OverviewOutput)
def overview(profile_id: str, svc: TrackingService = Depends(get_tracking)) -> OverviewOutput:
    """Due follow-ups, upcoming interviews and funnel metrics for one profile."""
    try:
        data = svc.overview(profile_id)
    except _ERRORS as error:
        raise _fail(error) from error
    return OverviewOutput(
        due_follow_ups=[FollowUpOutput.model_validate(f) for f in data.due_follow_ups],
        upcoming_interviews=[InterviewOutput.model_validate(i) for i in data.upcoming_interviews],
        metrics=MetricsOutput(**vars(data.metrics)),
    )


@router.post("/jobs/{job_id}/transition", response_model=TransitionOutput)
def transition(job_id: str, payload: TransitionInput, svc: TrackingService = Depends(get_tracking)) -> TransitionOutput:
    """Move a job through the profile's workflow (used by the pipeline board). 409 if not allowed."""
    try:
        new = svc.transition(payload.profile_id, job_id, payload.to_status, payload.actor, payload.reason)
    except _ERRORS as error:
        raise _fail(error) from error
    return TransitionOutput(job_id=job_id, profile_id=payload.profile_id, status=new.value)
