from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerflow.api.schemas.profiles import (
    AchievementInput,
    AchievementOutput,
    ContactInput,
    ContactOutput,
    ExperienceInput,
    ExperienceOutput,
    ProfileInput,
    ProfileOutput,
)
from careerflow.application.profiles.service import ProfileNotFoundError, ProfileService
from careerflow.infrastructure.database.models import (
    ProfileContactModel,
    ProfileModel,
)
from careerflow.infrastructure.database.session import create_database_engine

router = APIRouter(prefix="/profiles", tags=["profiles"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


def get_service(session: Session = Depends(get_session)) -> ProfileService:
    return ProfileService(session)


def require_profile(service: ProfileService, profile_id: str) -> ProfileModel:
    try:
        return service.get_profile(profile_id)
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.get("", response_model=list[ProfileOutput])
def list_profiles(service: ProfileService = Depends(get_service)) -> list[ProfileOutput]:
    return [ProfileOutput.model_validate(item) for item in service.list_profiles()]


@router.post("", response_model=ProfileOutput, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileInput, service: ProfileService = Depends(get_service)) -> ProfileOutput:
    try:
        return ProfileOutput.model_validate(service.create_profile(payload.model_dump()))
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="profile slug already exists") from error


@router.get("/{profile_id}", response_model=ProfileOutput)
def get_profile(profile_id: str, service: ProfileService = Depends(get_service)) -> ProfileOutput:
    return ProfileOutput.model_validate(require_profile(service, profile_id))


@router.put("/{profile_id}", response_model=ProfileOutput)
def update_profile(
    profile_id: str, payload: ProfileInput, service: ProfileService = Depends(get_service)
) -> ProfileOutput:
    try:
        return ProfileOutput.model_validate(service.update_profile(profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="profile slug already exists") from error


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str, service: ProfileService = Depends(get_service)) -> None:
    try:
        service.delete_profile(profile_id)
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.get("/{profile_id}/contact", response_model=ContactOutput | None)
def get_contact(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> ContactOutput | None:
    require_profile(service, profile_id)
    contact = service.session.get(ProfileContactModel, profile_id)
    return ContactOutput.model_validate(contact) if contact else None


@router.put("/{profile_id}/contact", response_model=ContactOutput)
def replace_contact(
    profile_id: str, payload: ContactInput, service: ProfileService = Depends(get_service)
) -> ContactOutput:
    try:
        return ContactOutput.model_validate(service.replace_contact(profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.get("/{profile_id}/experiences", response_model=list[ExperienceOutput])
def list_experiences(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> list[ExperienceOutput]:
    try:
        return [ExperienceOutput.model_validate(item) for item in service.list_experiences(profile_id)]
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.post("/{profile_id}/experiences", response_model=ExperienceOutput, status_code=status.HTTP_201_CREATED)
def add_experience(
    profile_id: str, payload: ExperienceInput, service: ProfileService = Depends(get_service)
) -> ExperienceOutput:
    try:
        return ExperienceOutput.model_validate(service.add_experience(profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.get("/{profile_id}/achievements", response_model=list[AchievementOutput])
def list_achievements(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> list[AchievementOutput]:
    try:
        return [AchievementOutput.model_validate(item) for item in service.list_achievements(profile_id)]
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error


@router.post("/{profile_id}/achievements", response_model=AchievementOutput, status_code=status.HTTP_201_CREATED)
def add_achievement(
    profile_id: str, payload: AchievementInput, service: ProfileService = Depends(get_service)
) -> AchievementOutput:
    try:
        return AchievementOutput.model_validate(service.add_achievement(profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found") from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


