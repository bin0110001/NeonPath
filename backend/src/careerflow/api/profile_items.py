"""Profile-scoped CRUD routes: generic items, preferences, skills/aliases, export/import.

Every record id is resolved *through* its profile; an id that belongs to a different
profile is reported as 404 and nothing changes.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from careerflow.api.profiles import get_service, require_profile
from careerflow.api.schemas.profiles import (
    AchievementExport,
    AchievementInput,
    AchievementOutput,
    AliasInput,
    ContactInput,
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
    RoleTargetInput,
    RoleTargetOutput,
    ScoringPreferenceInput,
    ScoringPreferenceOutput,
    SearchPreferenceInput,
    SearchPreferenceOutput,
    SkillInput,
    SkillOutput,
    SkillUpdate,
)
from careerflow.application.profiles.service import (
    ProfileItemNotFoundError,
    ProfileNotFoundError,
    ProfileService,
)
from careerflow.infrastructure.database.models import (
    AchievementModel,
    EducationModel,
    ExperienceModel,
    PortfolioItemModel,
    ProfileContactModel,
    ProfileSkillModel,
    RoleFamilyModel,
    RoleTargetModel,
    ScoringPreferenceModel,
    SearchPreferenceModel,
    SkillAliasModel,
    SkillModel,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _not_found(error: Exception) -> HTTPException:
    detail = "profile not found" if isinstance(error, ProfileNotFoundError) else "record not found"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _guarded(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except (ProfileNotFoundError, ProfileItemNotFoundError) as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


def _crud(
    path: str,
    model: type[Any],
    input_schema: type[BaseModel],
    output_schema: type[BaseModel],
    create: bool = True,
    list_route: bool = True,
) -> None:
    """Register list/create/get/put/delete routes for one profile-owned record type."""
    base = f"/{{profile_id}}/{path}"

    if list_route:

        @router.get(base, response_model=list[output_schema], name=f"list_{path}")  # type: ignore[valid-type]
        def list_items(profile_id: str, service: ProfileService = Depends(get_service)) -> Any:
            items = _guarded(lambda: service.list_profile_items(model, profile_id))
            return [output_schema.model_validate(i, from_attributes=True) for i in items]

    if create:

        @router.post(base, response_model=output_schema, status_code=201, name=f"add_{path}")
        def add_item(
            profile_id: str,
            payload: input_schema,  # type: ignore[valid-type]
            service: ProfileService = Depends(get_service),
        ) -> Any:
            item = _guarded(lambda: service.add_profile_item(model, profile_id, payload.model_dump()))  # type: ignore[attr-defined]
            return output_schema.model_validate(item, from_attributes=True)

    @router.get(base + "/{item_id}", response_model=output_schema, name=f"get_{path}")
    def get_item(
        profile_id: str, item_id: str, service: ProfileService = Depends(get_service)
    ) -> Any:
        item = _guarded(lambda: service.get_profile_item(model, profile_id, item_id))
        return output_schema.model_validate(item, from_attributes=True)

    @router.put(base + "/{item_id}", response_model=output_schema, name=f"update_{path}")
    def update_item(
        profile_id: str,
        item_id: str,
        payload: input_schema,  # type: ignore[valid-type]
        service: ProfileService = Depends(get_service),
    ) -> Any:
        item = _guarded(
            lambda: service.update_profile_item(model, profile_id, item_id, payload.model_dump())  # type: ignore[attr-defined]
        )
        return output_schema.model_validate(item, from_attributes=True)

    @router.delete(base + "/{item_id}", status_code=204, name=f"delete_{path}")
    def delete_item(
        profile_id: str, item_id: str, service: ProfileService = Depends(get_service)
    ) -> None:
        _guarded(lambda: service.delete_profile_item(model, profile_id, item_id))


# Experiences/achievements keep their list/create routes in profiles.py (ordering, link checks).
_crud("experiences", ExperienceModel, ExperienceInput, ExperienceOutput, create=False, list_route=False)
_crud("achievements", AchievementModel, AchievementInput, AchievementOutput, create=False, list_route=False)
_crud("education", EducationModel, EducationInput, EducationOutput)
_crud("portfolio", PortfolioItemModel, PortfolioInput, PortfolioOutput)
_crud("role-families", RoleFamilyModel, RoleFamilyInput, RoleFamilyOutput)
_crud("role-targets", RoleTargetModel, RoleTargetInput, RoleTargetOutput)


# -- preferences ---------------------------------------------------------------------------


@router.get("/{profile_id}/search-preferences", response_model=SearchPreferenceOutput | None)
def get_search_preferences(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> SearchPreferenceOutput | None:
    require_profile(service, profile_id)
    row = service.get_search_preferences(profile_id)
    return SearchPreferenceOutput.model_validate(row) if row else None


@router.put("/{profile_id}/search-preferences", response_model=SearchPreferenceOutput)
def replace_search_preferences(
    profile_id: str,
    payload: SearchPreferenceInput,
    service: ProfileService = Depends(get_service),
) -> SearchPreferenceOutput:
    require_profile(service, profile_id)
    row = service.replace_profile_item(SearchPreferenceModel, profile_id, payload.model_dump())
    return SearchPreferenceOutput.model_validate(row)


@router.get("/{profile_id}/scoring-preferences", response_model=ScoringPreferenceOutput | None)
def get_scoring_preferences(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> ScoringPreferenceOutput | None:
    require_profile(service, profile_id)
    row = service.get_scoring_preferences(profile_id)
    return ScoringPreferenceOutput.model_validate(row) if row else None


@router.put("/{profile_id}/scoring-preferences", response_model=ScoringPreferenceOutput)
def replace_scoring_preferences(
    profile_id: str,
    payload: ScoringPreferenceInput,
    service: ProfileService = Depends(get_service),
) -> ScoringPreferenceOutput:
    require_profile(service, profile_id)
    row = service.replace_profile_item(ScoringPreferenceModel, profile_id, payload.model_dump())
    return ScoringPreferenceOutput.model_validate(row)


# -- skills --------------------------------------------------------------------------------


def _skill_output(service: ProfileService, link: ProfileSkillModel, skill: SkillModel) -> SkillOutput:
    aliases = sorted(
        service.session.scalars(
            select(SkillAliasModel.alias).where(SkillAliasModel.skill_id == skill.id)
        )
    )
    return SkillOutput(
        profile_id=link.profile_id,
        skill_id=skill.id,
        canonical_name=skill.canonical_name,
        category=skill.category,
        proficiency=link.proficiency,
        years_experience=link.years_experience,
        last_used_year=link.last_used_year,
        evidence_notes=link.evidence_notes,
        verified=link.verified,
        aliases=aliases,
    )


@router.get("/{profile_id}/skills", response_model=list[SkillOutput])
def list_skills(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> list[SkillOutput]:
    pairs = _guarded(lambda: service.list_profile_skills(profile_id))
    return [_skill_output(service, link, skill) for link, skill in pairs]


@router.post("/{profile_id}/skills", response_model=SkillOutput, status_code=201)
def add_skill(
    profile_id: str, payload: SkillInput, service: ProfileService = Depends(get_service)
) -> SkillOutput:
    link = _guarded(lambda: service.add_skill(profile_id, payload.model_dump()))
    skill = service.session.get(SkillModel, link.skill_id)
    assert skill is not None
    return _skill_output(service, link, skill)


@router.put("/{profile_id}/skills/{skill_id}", response_model=SkillOutput)
def update_skill(
    profile_id: str,
    skill_id: str,
    payload: SkillUpdate,
    service: ProfileService = Depends(get_service),
) -> SkillOutput:
    link, skill = _guarded(
        lambda: service.update_profile_skill(
            profile_id, skill_id, payload.model_dump(exclude_unset=True)
        )
    )
    return _skill_output(service, link, skill)


@router.delete("/{profile_id}/skills/{skill_id}", status_code=204)
def remove_skill(
    profile_id: str, skill_id: str, service: ProfileService = Depends(get_service)
) -> None:
    _guarded(lambda: service.remove_profile_skill(profile_id, skill_id))


@router.get("/{profile_id}/skills/{skill_id}/aliases", response_model=list[str])
def list_aliases(
    profile_id: str, skill_id: str, service: ProfileService = Depends(get_service)
) -> list[str]:
    result: list[str] = _guarded(lambda: service.list_skill_aliases(profile_id, skill_id))
    return result


@router.post("/{profile_id}/skills/{skill_id}/aliases", response_model=list[str], status_code=201)
def add_alias(
    profile_id: str,
    skill_id: str,
    payload: AliasInput,
    service: ProfileService = Depends(get_service),
) -> list[str]:
    try:
        service.add_skill_alias(profile_id, skill_id, payload.alias)
    except (ProfileNotFoundError, ProfileItemNotFoundError) as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    return service.list_skill_aliases(profile_id, skill_id)


@router.delete("/{profile_id}/skills/{skill_id}/aliases/{alias}", status_code=204)
def remove_alias(
    profile_id: str, skill_id: str, alias: str, service: ProfileService = Depends(get_service)
) -> None:
    _guarded(lambda: service.remove_skill_alias(profile_id, skill_id, alias))


# -- export / import (versioned) -------------------------------------------------------------


@router.get("/{profile_id}/export", response_model=ProfileExport)
def export_profile(
    profile_id: str, service: ProfileService = Depends(get_service)
) -> ProfileExport:
    profile = require_profile(service, profile_id)
    experiences = service.list_experiences(profile_id)
    index = {e.id: i for i, e in enumerate(experiences)}
    achievements = []
    for item in service.list_achievements(profile_id):
        exported = AchievementExport.model_validate(item, from_attributes=True)
        exported.experience_index = index.get(item.experience_id or "")
        exported.experience_id = None
        achievements.append(exported)
    search = service.get_search_preferences(profile_id)
    scoring = service.get_scoring_preferences(profile_id)

    def items(model: type[Any], schema: type[Any]) -> list[Any]:
        return [schema.model_validate(i, from_attributes=True) for i in service.list_profile_items(model, profile_id)]

    return ProfileExport(
        profile=ProfileInput.model_validate(profile, from_attributes=True),
        contact=ContactInput.model_validate(profile.contact, from_attributes=True)
        if profile.contact
        else None,
        experiences=[ExperienceInput.model_validate(e, from_attributes=True) for e in experiences],
        achievements=achievements,
        skills=[
            SkillInput.model_validate(_skill_output(service, link, skill).model_dump())
            for link, skill in service.list_profile_skills(profile_id)
        ],
        education=items(EducationModel, EducationInput),
        portfolio=items(PortfolioItemModel, PortfolioInput),
        role_families=items(RoleFamilyModel, RoleFamilyInput),
        role_targets=items(RoleTargetModel, RoleTargetInput),
        search_preferences=SearchPreferenceInput.model_validate(search, from_attributes=True)
        if search
        else None,
        scoring_preferences=ScoringPreferenceInput.model_validate(scoring, from_attributes=True)
        if scoring
        else None,
    )


@router.post("/import", response_model=ProfileOutput, status_code=status.HTTP_201_CREATED)
def import_profile(
    payload: ProfileExport, service: ProfileService = Depends(get_service)
) -> ProfileOutput:
    if payload.schema_version not in (1, 2):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported export schema"
        )
    try:
        profile = service.create_profile(payload.profile.model_dump())
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="profile slug already exists"
        ) from error
    profile_id = profile.id
    try:
        if payload.contact:
            service.replace_contact(profile_id, payload.contact.model_dump())
        created = [service.add_experience(profile_id, e.model_dump()) for e in payload.experiences]
        for achievement in payload.achievements:
            values = achievement.model_dump(exclude={"experience_index"})
            position = achievement.experience_index
            linked = position is not None and 0 <= position < len(created)
            values["experience_id"] = created[position].id if linked else None  # type: ignore[index]
            service.add_achievement(profile_id, values)
        for skill in payload.skills:
            service.add_skill(profile_id, skill.model_dump())
        groups: tuple[tuple[type[Any], list[Any]], ...] = (
            (EducationModel, payload.education),
            (PortfolioItemModel, payload.portfolio),
            (RoleFamilyModel, payload.role_families),
            (RoleTargetModel, payload.role_targets),
        )
        for model, records in groups:
            for record in records:
                service.add_profile_item(model, profile_id, record.model_dump())
        if payload.search_preferences:
            service.replace_profile_item(
                SearchPreferenceModel, profile_id, payload.search_preferences.model_dump()
            )
        if payload.scoring_preferences:
            service.replace_profile_item(
                ScoringPreferenceModel, profile_id, payload.scoring_preferences.model_dump()
            )
    except (IntegrityError, ValueError) as error:
        service.session.rollback()
        _discard_partial_import(service, profile_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"import failed: {error}"
        ) from error
    return ProfileOutput.model_validate(profile)


def _discard_partial_import(service: ProfileService, profile_id: str) -> None:
    """Remove everything created for a failed import so no half-imported profile remains."""
    session = service.session
    for model in (
        ProfileContactModel,
        AchievementModel,
        ExperienceModel,
        EducationModel,
        PortfolioItemModel,
        RoleFamilyModel,
        RoleTargetModel,
        ProfileSkillModel,
        SearchPreferenceModel,
        ScoringPreferenceModel,
    ):
        for row in session.scalars(select(model).where(model.profile_id == profile_id)):
            session.delete(row)
    session.flush()
    service.delete_profile(profile_id)
