from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import (
    AchievementModel,
    ExperienceModel,
    ProfileContactModel,
    ProfileModel,
    ProfileSkillModel,
    RoleFamilyModel,
    RoleTargetModel,
    ScoringPreferenceModel,
    SearchPreferenceModel,
    SkillAliasModel,
    SkillModel,
)

T = TypeVar("T")


class ProfileNotFoundError(Exception):
    pass


class ProfileService:
    """Profile use cases; HTTP and ORM serialization remain outside this layer."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_profiles(self) -> list[ProfileModel]:
        return list(self.session.scalars(select(ProfileModel).order_by(ProfileModel.display_name)))

    def get_profile(self, profile_id: str) -> ProfileModel:
        profile = self.session.get(ProfileModel, profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        return profile

    def create_profile(self, values: dict[str, object]) -> ProfileModel:
        profile = ProfileModel(**values)
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def update_profile(self, profile_id: str, values: dict[str, object]) -> ProfileModel:
        profile = self.get_profile(profile_id)
        for name, value in values.items():
            setattr(profile, name, value)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def delete_profile(self, profile_id: str) -> None:
        profile = self.get_profile(profile_id)
        self.session.delete(profile)
        self.session.commit()

    def replace_contact(self, profile_id: str, values: dict[str, object]) -> ProfileContactModel:
        self.get_profile(profile_id)
        contact = self.session.get(ProfileContactModel, profile_id)
        if contact is None:
            contact = ProfileContactModel(profile_id=profile_id, **values)
            self.session.add(contact)
        else:
            for name, value in values.items():
                setattr(contact, name, value)
        self.session.commit()
        self.session.refresh(contact)
        return contact

    def add_experience(self, profile_id: str, values: dict[str, object]) -> ExperienceModel:
        self.get_profile(profile_id)
        experience = ExperienceModel(profile_id=profile_id, **values)
        self.session.add(experience)
        self.session.commit()
        self.session.refresh(experience)
        return experience

    def list_experiences(self, profile_id: str) -> list[ExperienceModel]:
        self.get_profile(profile_id)
        statement = select(ExperienceModel).where(ExperienceModel.profile_id == profile_id)
        return list(self.session.scalars(statement.order_by(ExperienceModel.sort_order)))

    def add_achievement(self, profile_id: str, values: dict[str, object]) -> AchievementModel:
        self.get_profile(profile_id)
        experience_id = values.get("experience_id")
        if experience_id is not None:
            experience = self.session.get(ExperienceModel, experience_id)
            if experience is None or experience.profile_id != profile_id:
                raise ValueError("experience must belong to the selected profile")
        achievement = AchievementModel(profile_id=profile_id, **values)
        self.session.add(achievement)
        self.session.commit()
        self.session.refresh(achievement)
        return achievement

    def list_achievements(self, profile_id: str) -> list[AchievementModel]:
        self.get_profile(profile_id)
        return list(
            self.session.scalars(
                select(AchievementModel).where(AchievementModel.profile_id == profile_id)
            )
        )

    def add_skill(self, profile_id: str, values: dict[str, object]) -> ProfileSkillModel:
        self.get_profile(profile_id)
        name = str(values.pop("canonical_name")).strip()
        aliases = values.pop("aliases", [])
        category = values.pop("category", None)
        skill = self.session.scalar(select(SkillModel).where(SkillModel.canonical_name == name))
        if skill is None:
            skill = SkillModel(canonical_name=name, category=category)
            self.session.add(skill)
            self.session.flush()
        for alias in aliases if isinstance(aliases, list) else []:
            if isinstance(alias, str) and self.session.get(SkillAliasModel, alias) is None:
                self.session.add(SkillAliasModel(alias=alias, skill_id=skill.id))
        profile_skill = self.session.get(ProfileSkillModel, (profile_id, skill.id))
        if profile_skill is None:
            profile_skill = ProfileSkillModel(profile_id=profile_id, skill_id=skill.id, **values)
            self.session.add(profile_skill)
        self.session.commit()
        return profile_skill

    def add_profile_item(
        self, model: type[T], profile_id: str, values: dict[str, object]
    ) -> T:
        self.get_profile(profile_id)
        item = model(profile_id=profile_id, **values)  # type: ignore[call-arg]
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def list_profile_items(self, model: type[T], profile_id: str) -> list[T]:
        self.get_profile(profile_id)
        profile_column = model.profile_id  # type: ignore[attr-defined]
        return list(self.session.scalars(select(model).where(profile_column == profile_id)))

    def replace_profile_item(
        self, model: type[T], profile_id: str, values: dict[str, object]
    ) -> T:
        self.get_profile(profile_id)
        item = self.session.get(model, profile_id)
        if item is None:
            item = model(profile_id=profile_id, **values)  # type: ignore[call-arg]
            self.session.add(item)
        else:
            for name, value in values.items():
                setattr(item, name, value)
        self.session.commit()
        self.session.refresh(item)
        return item

    # Role family methods
    def list_role_families(self, profile_id: str) -> list[RoleFamilyModel]:
        self.get_profile(profile_id)
        statement = select(RoleFamilyModel).where(RoleFamilyModel.profile_id == profile_id)
        return list(self.session.scalars(statement))

    def add_role_family(self, profile_id: str, values: dict[str, object]) -> object:
        self.get_profile(profile_id)
        role_family = RoleFamilyModel(profile_id=profile_id, **values)
        self.session.add(role_family)
        self.session.commit()
        self.session.refresh(role_family)
        return role_family

    # Role target methods
    def list_role_targets(self, profile_id: str) -> list[RoleTargetModel]:
        self.get_profile(profile_id)
        statement = select(RoleTargetModel).where(RoleTargetModel.profile_id == profile_id)
        return list(self.session.scalars(statement))

    def add_role_target(self, profile_id: str, values: dict[str, object]) -> object:
        self.get_profile(profile_id)
        role_target = RoleTargetModel(profile_id=profile_id, **values)
        self.session.add(role_target)
        self.session.commit()
        self.session.refresh(role_target)
        return role_target

    # Search preferences methods
    def get_search_preferences(self, profile_id: str) -> SearchPreferenceModel | None:
        self.get_profile(profile_id)
        statement = select(SearchPreferenceModel).where(SearchPreferenceModel.profile_id == profile_id)
        return self.session.scalars(statement).first()

    def add_or_update_search_preferences(self, profile_id: str, values: dict[str, object]) -> object:
        self.get_profile(profile_id)
        existing = self.session.get(SearchPreferenceModel, profile_id)
        if existing:
            for name, value in values.items():
                setattr(existing, name, value)
        else:
            existing = SearchPreferenceModel(profile_id=profile_id, **values)
            self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing

    # Scoring preferences methods
    def get_scoring_preferences(self, profile_id: str) -> ScoringPreferenceModel | None:
        self.get_profile(profile_id)
        statement = select(ScoringPreferenceModel).where(ScoringPreferenceModel.profile_id == profile_id)
        return self.session.scalars(statement).first()

    def add_or_update_scoring_preferences(self, profile_id: str, values: dict[str, object]) -> object:
        self.get_profile(profile_id)
        existing = self.session.get(ScoringPreferenceModel, profile_id)
        if existing:
            for name, value in values.items():
                setattr(existing, name, value)
        else:
            existing = ScoringPreferenceModel(profile_id=profile_id, **values)
            self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing
