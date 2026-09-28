from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerflow.api.schemas.profiles import (
    AchievementInput,
    AchievementOutput,
    ContactInput,
    ContactOutput,
    EducationInput,
    EducationOutput,
    ExperienceInput,
    ExperienceOutput,
    PortfolioInput,
    PortfolioOutput,
    ProfileExport,
    ProfileInput,
    ProfileOutput,
    RoleFamilyInput,
    RoleFamilyOutput,
    ScoringPreferenceInput,
    ScoringPreferenceOutput,
    SearchPreferenceInput,
    SearchPreferenceOutput,
    SkillInput,
    SkillOutput,
)
from careerflow.application.profiles.service import ProfileNotFoundError, ProfileService
from careerflow.infrastructure.database.models import (
    EducationModel,
    PortfolioItemModel,
    ProfileContactModel,
    ProfileModel,
    RoleFamilyModel,
    ScoringPreferenceModel,
    SearchPreferenceModel,
    SkillModel,
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


@router.get("/{profile_id}/export", response_model=ProfileExport)
def export_profile(profile_id: str, service: ProfileService = Depends(get_service)) -> ProfileExport:
    profile = require_profile(service, profile_id)
    return ProfileExport(
        profile=ProfileInput.model_validate(profile, from_attributes=True),
        contact=ContactInput.model_validate(profile.contact, from_attributes=True) if profile.contact else None,
        experiences=[ExperienceInput.model_validate(item, from_attributes=True) for item in service.list_experiences(profile_id)],
        achievements=[AchievementInput.model_validate(item, from_attributes=True) for item in service.list_achievements(profile_id)],
    )


@router.post("/import", response_model=ProfileOutput, status_code=status.HTTP_201_CREATED)
def import_profile(payload: ProfileExport, service: ProfileService = Depends(get_service)) -> ProfileOutput:
    if payload.schema_version != 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported export schema")
    try:
        profile = service.create_profile(payload.profile.model_dump())
        if payload.contact:
            service.replace_contact(profile.id, payload.contact.model_dump())
        for experience in payload.experiences:
            service.add_experience(profile.id, experience.model_dump())
        for achievement in payload.achievements:
            service.add_achievement(profile.id, achievement.model_dump())
        return ProfileOutput.model_validate(profile)
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="profile slug already exists") from error


@router.get("/{profile_id}/education", response_model=list[EducationOutput])
def list_education(profile_id: str, service: ProfileService = Depends(get_service)) -> list[EducationOutput]:
    try:
        return [EducationOutput.model_validate(item) for item in service.list_profile_items(EducationModel, profile_id)]
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.post("/{profile_id}/education", response_model=EducationOutput, status_code=201)
def add_education(profile_id: str, payload: EducationInput, service: ProfileService = Depends(get_service)) -> EducationOutput:
    try:
        return EducationOutput.model_validate(service.add_profile_item(EducationModel, profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.get("/{profile_id}/portfolio", response_model=list[PortfolioOutput])
def list_portfolio(profile_id: str, service: ProfileService = Depends(get_service)) -> list[PortfolioOutput]:
    try:
        return [PortfolioOutput.model_validate(item) for item in service.list_profile_items(PortfolioItemModel, profile_id)]
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.post("/{profile_id}/portfolio", response_model=PortfolioOutput, status_code=201)
def add_portfolio(profile_id: str, payload: PortfolioInput, service: ProfileService = Depends(get_service)) -> PortfolioOutput:
    try:
        return PortfolioOutput.model_validate(service.add_profile_item(PortfolioItemModel, profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.get("/{profile_id}/role-families", response_model=list[RoleFamilyOutput])
def list_role_families(profile_id: str, service: ProfileService = Depends(get_service)) -> list[RoleFamilyOutput]:
    try:
        return [RoleFamilyOutput.model_validate(item) for item in service.list_profile_items(RoleFamilyModel, profile_id)]
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.post("/{profile_id}/role-families", response_model=RoleFamilyOutput, status_code=201)
def add_role_family(profile_id: str, payload: RoleFamilyInput, service: ProfileService = Depends(get_service)) -> RoleFamilyOutput:
    try:
        return RoleFamilyOutput.model_validate(service.add_profile_item(RoleFamilyModel, profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.put("/{profile_id}/search-preferences", response_model=SearchPreferenceOutput)
def replace_search_preferences(profile_id: str, payload: SearchPreferenceInput, service: ProfileService = Depends(get_service)) -> SearchPreferenceOutput:
    try:
        return SearchPreferenceOutput.model_validate(service.replace_profile_item(SearchPreferenceModel, profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.put("/{profile_id}/scoring-preferences", response_model=ScoringPreferenceOutput)
def replace_scoring_preferences(profile_id: str, payload: ScoringPreferenceInput, service: ProfileService = Depends(get_service)) -> ScoringPreferenceOutput:
    try:
        return ScoringPreferenceOutput.model_validate(service.replace_profile_item(ScoringPreferenceModel, profile_id, payload.model_dump()))
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error


@router.post("/{profile_id}/skills", response_model=SkillOutput, status_code=201)
def add_skill(profile_id: str, payload: SkillInput, service: ProfileService = Depends(get_service)) -> SkillOutput:
    try:
        profile_skill = service.add_skill(profile_id, payload.model_dump())
        skill = service.session.get(SkillModel, profile_skill.skill_id)
        assert skill is not None
        return SkillOutput(profile_id=profile_id, canonical_name=skill.canonical_name, category=skill.category, proficiency=profile_skill.proficiency, years_experience=profile_skill.years_experience, last_used_year=profile_skill.last_used_year, evidence_notes=profile_skill.evidence_notes, verified=profile_skill.verified)
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail="profile not found") from error
