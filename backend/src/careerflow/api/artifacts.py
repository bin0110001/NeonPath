from collections.abc import Generator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.application.artifacts.service import ArtifactError, ArtifactService
from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileNotFoundError
from careerflow.infrastructure.artifacts.registry import RENDERERS, UnknownFormatError, get_renderer
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(tags=["artifacts"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


class ArtifactCreate(BaseModel):
    format: str = "markdown"
    job_id: str | None = None
    redacted: bool = False
    include_cover_letter_notes: bool = False


class ArtifactOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    job_id: str | None
    kind: str
    format: str
    version: int
    renderer_version: str
    redacted: bool
    content_sha256: str
    created_at: datetime
    size_bytes: int = Field(default=0)


class RerenderOutput(BaseModel):
    artifact_id: str
    version: int
    matches_stored: bool
    content_sha256: str


def _out(row: object) -> ArtifactOutput:
    out = ArtifactOutput.model_validate(row)
    out.size_bytes = len(getattr(row, "content", b""))
    return out


def _fail(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if isinstance(error, JobNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if isinstance(error, ProfileItemNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


_ERRORS = (ProfileNotFoundError, JobNotFoundError, ProfileItemNotFoundError, UnknownFormatError, ArtifactError)


@router.get("/artifact-formats", response_model=list[str])
def formats() -> list[str]:
    return sorted(RENDERERS)


@router.get("/profiles/{profile_id}/artifacts", response_model=list[ArtifactOutput])
def list_artifacts(profile_id: str, job_id: str | None = None, session: Session = Depends(get_session)) -> list[ArtifactOutput]:
    try:
        return [_out(a) for a in ArtifactService(session).list(profile_id, job_id)]
    except _ERRORS as error:
        raise _fail(error) from error


@router.post("/profiles/{profile_id}/artifacts", response_model=ArtifactOutput, status_code=201)
def create_artifact(profile_id: str, payload: ArtifactCreate, session: Session = Depends(get_session)) -> ArtifactOutput:
    """Render a new version. ``redacted=true`` produces a public copy without contact details."""
    try:
        row = ArtifactService(session).create(
            profile_id, payload.job_id, payload.format, payload.redacted, payload.include_cover_letter_notes
        )
    except _ERRORS as error:
        raise _fail(error) from error
    return _out(row)


@router.get("/profiles/{profile_id}/artifacts/{artifact_id}", response_model=ArtifactOutput)
def get_artifact(profile_id: str, artifact_id: str, session: Session = Depends(get_session)) -> ArtifactOutput:
    try:
        return _out(ArtifactService(session).get(profile_id, artifact_id))
    except _ERRORS as error:
        raise _fail(error) from error


@router.get("/profiles/{profile_id}/artifacts/{artifact_id}/download")
def download_artifact(profile_id: str, artifact_id: str, session: Session = Depends(get_session)) -> Response:
    try:
        row = ArtifactService(session).get(profile_id, artifact_id)
    except _ERRORS as error:
        raise _fail(error) from error
    renderer = get_renderer(row.format)
    filename = f"resume-v{row.version}{'-public' if row.redacted else ''}.{renderer.extension}"
    return Response(
        content=row.content,
        media_type=renderer.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"},
    )


@router.post("/profiles/{profile_id}/artifacts/{artifact_id}/rerender", response_model=RerenderOutput)
def rerender_artifact(profile_id: str, artifact_id: str, session: Session = Depends(get_session)) -> RerenderOutput:
    """Rebuild this version from its retained inputs and report whether it matches the stored bytes."""
    try:
        result = ArtifactService(session).rerender(profile_id, artifact_id)
    except _ERRORS as error:
        raise _fail(error) from error
    import hashlib

    return RerenderOutput(
        artifact_id=artifact_id,
        version=result.artifact.version,
        matches_stored=result.matches_stored,
        content_sha256=hashlib.sha256(result.content).hexdigest(),
    )
