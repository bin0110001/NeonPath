"""Resume variants and application packages (plan section 13). Always profile-scoped."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobNotFoundError
from careerflow.application.profiles.service import ProfileItemNotFoundError, ProfileService
from careerflow.infrastructure.database.models import (
    AchievementModel,
    ApplicationPackageModel,
    ExperienceModel,
    JobModel,
    ResumeTemplateModel,
    ResumeVariantModel,
    RoleFamilyModel,
)

DEFAULT_TEMPLATE = "Plain Markdown"


class ResumeLinkError(ValueError):
    """A referenced record does not exist or belongs to another profile."""


class ResumeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.profiles = ProfileService(session)

    # -- templates (global) -------------------------------------------------------------

    def ensure_default_template(self) -> ResumeTemplateModel:
        template = self.session.scalars(
            select(ResumeTemplateModel).where(ResumeTemplateModel.name == DEFAULT_TEMPLATE)
        ).first()
        if template is None:
            template = ResumeTemplateModel(
                name=DEFAULT_TEMPLATE,
                format="markdown",
                layout_config={"sections": ["summary", "skills", "experience", "achievements", "education"]},
                theme_config={},
            )
            self.session.add(template)
            self.session.commit()
        return template

    def list_templates(self) -> list[ResumeTemplateModel]:
        self.ensure_default_template()
        return list(self.session.scalars(select(ResumeTemplateModel).order_by(ResumeTemplateModel.name)))

    # -- links ------------------------------------------------------------------------------

    def _owned(self, model: type[Any], profile_id: str, ids: list[str], what: str) -> None:
        for record_id in ids:
            row = self.session.get(model, record_id)
            if row is None or row.profile_id != profile_id:
                raise ResumeLinkError(f"{what} {record_id} does not belong to this profile")

    def _check_variant(self, profile_id: str, values: dict[str, Any]) -> None:
        if values.get("role_family_id"):
            self._owned(RoleFamilyModel, profile_id, [values["role_family_id"]], "role family")
        if values.get("template_id") and self.session.get(ResumeTemplateModel, values["template_id"]) is None:
            raise ResumeLinkError(f"template {values['template_id']} does not exist")
        self._owned(ExperienceModel, profile_id, list(values.get("selected_experience_ids") or []), "experience")
        self._owned(AchievementModel, profile_id, list(values.get("selected_achievement_ids") or []), "achievement")

    # -- variants ---------------------------------------------------------------------------

    def list_variants(self, profile_id: str) -> list[ResumeVariantModel]:
        return self.profiles.list_profile_items(ResumeVariantModel, profile_id)

    def get_variant(self, profile_id: str, variant_id: str) -> ResumeVariantModel:
        return self.profiles.get_profile_item(ResumeVariantModel, profile_id, variant_id)

    def create_variant(self, profile_id: str, values: dict[str, Any]) -> ResumeVariantModel:
        self.profiles.get_profile(profile_id)
        self._check_variant(profile_id, values)
        if not values.get("template_id"):
            values["template_id"] = self.ensure_default_template().id
        return self.profiles.add_profile_item(ResumeVariantModel, profile_id, values)

    def update_variant(self, profile_id: str, variant_id: str, values: dict[str, Any]) -> ResumeVariantModel:
        self.get_variant(profile_id, variant_id)
        self._check_variant(profile_id, values)
        return self.profiles.update_profile_item(ResumeVariantModel, profile_id, variant_id, values)

    def delete_variant(self, profile_id: str, variant_id: str) -> None:
        self.get_variant(profile_id, variant_id)
        self.session.execute(
            update(ApplicationPackageModel)
            .where(ApplicationPackageModel.resume_variant_id == variant_id)
            .values(resume_variant_id=None)
        )
        self.profiles.delete_profile_item(ResumeVariantModel, profile_id, variant_id)

    # -- packages ---------------------------------------------------------------------------

    def list_packages(self, profile_id: str) -> list[ApplicationPackageModel]:
        return self.profiles.list_profile_items(ApplicationPackageModel, profile_id)

    def get_package(self, profile_id: str, package_id: str) -> ApplicationPackageModel:
        return self.profiles.get_profile_item(ApplicationPackageModel, profile_id, package_id)

    def package_for_job(self, profile_id: str, job_id: str) -> ApplicationPackageModel | None:
        self.profiles.get_profile(profile_id)
        return self.session.scalars(
            select(ApplicationPackageModel).where(
                ApplicationPackageModel.profile_id == profile_id, ApplicationPackageModel.job_id == job_id
            )
        ).first()

    def save_package(self, profile_id: str, job_id: str, values: dict[str, Any]) -> ApplicationPackageModel:
        """Create or replace the (single) package of this profile for this job."""
        self.profiles.get_profile(profile_id)
        if self.session.get(JobModel, job_id) is None:
            raise JobNotFoundError(job_id)
        if values.get("resume_variant_id"):
            self.get_variant(profile_id, values["resume_variant_id"])  # must be this profile's
        self._owned(AchievementModel, profile_id, list(values.get("recommended_achievement_ids") or []), "achievement")
        package = self.package_for_job(profile_id, job_id)
        if package is None:
            package = ApplicationPackageModel(profile_id=profile_id, job_id=job_id)
            self.session.add(package)
        for name, value in values.items():
            setattr(package, name, value)
        self.session.commit()
        self.session.refresh(package)
        return package

    def delete_package(self, profile_id: str, package_id: str) -> None:
        self.profiles.delete_profile_item(ApplicationPackageModel, profile_id, package_id)


__all__ = ["ProfileItemNotFoundError", "ResumeLinkError", "ResumeService"]
