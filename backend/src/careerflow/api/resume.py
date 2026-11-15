from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.application.ai.config import build_client
from careerflow.application.applications.prepare import PreparationService
from careerflow.application.applications.resume import ResumeLinkError, ResumeService
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileNotFoundError
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(tags=["resume"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


class TemplateOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    format: str
    layout_config: dict[str, Any]
    theme_config: dict[str, Any]


class VariantInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role_family_id: str | None = None
    template_id: str | None = None
    summary_strategy: str | None = None
    preferred_skill_categories: list[str] = Field(default_factory=list)
    selected_experience_ids: list[str] = Field(default_factory=list)
    selected_achievement_ids: list[str] = Field(default_factory=list)


class VariantOutput(VariantInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    created_at: datetime


class PackageInput(BaseModel):
    resume_variant_id: str | None = None
    recommended_achievement_ids: list[str] = Field(default_factory=list)
    recommended_skill_order: list[str] = Field(default_factory=list)
    summary_suggestion: str | None = None
    tailoring_notes: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    cover_letter_notes: list[str] = Field(default_factory=list)
    outreach_draft: str | None = None


class PackageOutput(PackageInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    job_id: str
    status: str
    approved_at: datetime | None
    provenance_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


def _error(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if isinstance(error, JobNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if isinstance(error, ProfileItemNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="record not found")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


_LOOKUP = (ProfileNotFoundError, ProfileItemNotFoundError, JobNotFoundError, ResumeLinkError)


@router.get("/resume-templates", response_model=list[TemplateOutput])
def list_templates(session: Session = Depends(get_session)) -> list[TemplateOutput]:
    return [TemplateOutput.model_validate(t) for t in ResumeService(session).list_templates()]


@router.get("/profiles/{profile_id}/resume-variants", response_model=list[VariantOutput])
def list_variants(profile_id: str, session: Session = Depends(get_session)) -> list[VariantOutput]:
    try:
        return [VariantOutput.model_validate(v) for v in ResumeService(session).list_variants(profile_id)]
    except _LOOKUP as error:
        raise _error(error) from error


@router.post("/profiles/{profile_id}/resume-variants", response_model=VariantOutput, status_code=201)
def create_variant(profile_id: str, payload: VariantInput, session: Session = Depends(get_session)) -> VariantOutput:
    try:
        return VariantOutput.model_validate(ResumeService(session).create_variant(profile_id, payload.model_dump()))
    except _LOOKUP as error:
        raise _error(error) from error


@router.get("/profiles/{profile_id}/resume-variants/{variant_id}", response_model=VariantOutput)
def get_variant(profile_id: str, variant_id: str, session: Session = Depends(get_session)) -> VariantOutput:
    try:
        return VariantOutput.model_validate(ResumeService(session).get_variant(profile_id, variant_id))
    except _LOOKUP as error:
        raise _error(error) from error


@router.put("/profiles/{profile_id}/resume-variants/{variant_id}", response_model=VariantOutput)
def update_variant(
    profile_id: str, variant_id: str, payload: VariantInput, session: Session = Depends(get_session)
) -> VariantOutput:
    try:
        row = ResumeService(session).update_variant(profile_id, variant_id, payload.model_dump())
    except _LOOKUP as error:
        raise _error(error) from error
    return VariantOutput.model_validate(row)


@router.delete("/profiles/{profile_id}/resume-variants/{variant_id}", status_code=204)
def delete_variant(profile_id: str, variant_id: str, session: Session = Depends(get_session)) -> None:
    try:
        ResumeService(session).delete_variant(profile_id, variant_id)
    except _LOOKUP as error:
        raise _error(error) from error


@router.get("/profiles/{profile_id}/packages", response_model=list[PackageOutput])
def list_packages(profile_id: str, session: Session = Depends(get_session)) -> list[PackageOutput]:
    try:
        return [PackageOutput.model_validate(p) for p in ResumeService(session).list_packages(profile_id)]
    except _LOOKUP as error:
        raise _error(error) from error


@router.get("/profiles/{profile_id}/packages/by-job/{job_id}", response_model=PackageOutput | None)
def package_for_job(profile_id: str, job_id: str, session: Session = Depends(get_session)) -> PackageOutput | None:
    try:
        row = ResumeService(session).package_for_job(profile_id, job_id)
    except _LOOKUP as error:
        raise _error(error) from error
    return None if row is None else PackageOutput.model_validate(row)


@router.put("/profiles/{profile_id}/packages/by-job/{job_id}", response_model=PackageOutput)
def save_package(
    profile_id: str, job_id: str, payload: PackageInput, session: Session = Depends(get_session)
) -> PackageOutput:
    """Manually edit/save the package of this profile for this job."""
    try:
        row = ResumeService(session).save_package(profile_id, job_id, payload.model_dump())
    except _LOOKUP as error:
        raise _error(error) from error
    return PackageOutput.model_validate(row)


@router.delete("/profiles/{profile_id}/packages/{package_id}", status_code=204)
def delete_package(profile_id: str, package_id: str, session: Session = Depends(get_session)) -> None:
    try:
        ResumeService(session).delete_package(profile_id, package_id)
    except _LOOKUP as error:
        raise _error(error) from error


class ClaimOutput(BaseModel):
    text: str
    basis: str  # evidence | inference | unverified
    evidence_ids: list[str]
    source: str  # deterministic | ai
    note: str | None = None


class ProposalOutput(BaseModel):
    """A suggestion only: nothing is stored until it is approved."""

    persisted: bool
    job_id: str
    profile_id: str
    existing_package_id: str | None
    resume_variant_id: str | None
    recommended_achievement_ids: list[str]
    recommended_skill_order: list[str]
    summary_suggestion: str | None
    tailoring_notes: list[str]
    cover_letter_notes: list[str]
    missing_evidence: list[str]
    outreach_draft: str | None
    warnings: list[str]
    claims: list[ClaimOutput]
    provenance: dict[str, Any]
    ai_note: str | None


class ApproveInput(PackageInput):
    provenance: dict[str, Any] = Field(default_factory=dict)


@router.post("/profiles/{profile_id}/jobs/{job_id}/prepare", response_model=ProposalOutput)
def prepare_application(profile_id: str, job_id: str, session: Session = Depends(get_session)) -> ProposalOutput:
    """Recommend how to prepare this application. Read-only: persists nothing, sends nothing."""
    service = PreparationService(session, build_client(session))
    try:
        proposal = service.propose(profile_id, job_id)
    except _LOOKUP as error:
        raise _error(error) from error
    return ProposalOutput(
        persisted=proposal.persisted,
        job_id=proposal.job_id,
        profile_id=proposal.profile_id,
        existing_package_id=proposal.existing_package_id,
        resume_variant_id=proposal.resume_variant_id,
        recommended_achievement_ids=proposal.recommended_achievement_ids,
        recommended_skill_order=proposal.recommended_skill_order,
        summary_suggestion=proposal.summary_suggestion,
        tailoring_notes=proposal.tailoring_notes,
        cover_letter_notes=proposal.cover_letter_notes,
        missing_evidence=proposal.missing_evidence,
        outreach_draft=proposal.outreach_draft,
        warnings=proposal.warnings,
        claims=[ClaimOutput(**vars(c)) for c in proposal.claims],
        provenance=proposal.provenance,
        ai_note=proposal.ai_note,
    )


@router.post("/profiles/{profile_id}/jobs/{job_id}/prepare/approve", response_model=PackageOutput)
def approve_preparation(
    profile_id: str, job_id: str, payload: ApproveInput, session: Session = Depends(get_session)
) -> PackageOutput:
    """The user's explicit approval: stores the (possibly edited) proposal as the package."""
    values = payload.model_dump(exclude={"provenance"})
    try:
        row = PreparationService(session).approve(profile_id, job_id, values, payload.provenance)
    except _LOOKUP as error:
        raise _error(error) from error
    return PackageOutput.model_validate(row)
