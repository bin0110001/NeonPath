"""Map ORM rows to the domain dataclasses the evaluator consumes."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.domain.jobs.model import Job
from careerflow.domain.profiles.model import (
    Profile,
    RoleFamily,
    RoleTarget,
    ScoringPreferences,
    SearchPreferences,
    SkillInfo,
)
from careerflow.infrastructure.database.models import (
    JobModel,
    ProfileModel,
    ProfileSkillModel,
    RoleFamilyModel,
    RoleTargetModel,
    ScoringPreferenceModel,
    SearchPreferenceModel,
    SkillAliasModel,
    SkillModel,
)


def to_domain_job(job: JobModel) -> Job:
    industry = (job.raw_metadata_json or {}).get("industry")
    return Job(
        title=job.title,
        company=job.company,
        description_text=job.description_text,
        location_text=job.location_text,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        industry=industry if isinstance(industry, str) else None,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        posted_at=job.posted_at,
        requirement_texts=[r.normalized_text for r in job.requirements],
    )


def load_skill_catalog(session: Session) -> list[SkillInfo]:
    aliases: dict[str, list[str]] = defaultdict(list)
    for alias in session.scalars(select(SkillAliasModel)):
        aliases[alias.skill_id].append(alias.alias)
    return [
        SkillInfo(name=s.canonical_name, aliases=aliases[s.id], category=s.category)
        for s in session.scalars(select(SkillModel))
    ]


def _search_prefs(row: SearchPreferenceModel | None) -> SearchPreferences | None:
    if row is None:
        return None
    return SearchPreferences(
        remote_preference=row.remote_preference,
        allowed_countries=list(row.allowed_countries or []),
        allowed_regions=list(row.allowed_regions or []),
        allowed_cities=list(row.allowed_cities or []),
        relocation_allowed=row.relocation_allowed,
        employment_types=list(row.employment_types or []),
        minimum_base_salary=row.minimum_base_salary,
        minimum_total_comp=row.minimum_total_comp,
        currency=row.currency,
        excluded_companies=list(row.excluded_companies or []),
        preferred_companies=list(row.preferred_companies or []),
        excluded_industries=list(row.excluded_industries or []),
        preferred_industries=list(row.preferred_industries or []),
    )


def to_domain_profile(
    session: Session, profile: ProfileModel, catalog: list[SkillInfo]
) -> Profile:
    by_name = {s.name: s for s in catalog}
    held = session.scalars(
        select(SkillModel)
        .join(ProfileSkillModel, ProfileSkillModel.skill_id == SkillModel.id)
        .where(ProfileSkillModel.profile_id == profile.id)
    )
    skills = [
        by_name.get(s.canonical_name) or SkillInfo(name=s.canonical_name, category=s.category)
        for s in held
    ]
    families = session.scalars(
        select(RoleFamilyModel).where(RoleFamilyModel.profile_id == profile.id)
    )
    targets = session.scalars(
        select(RoleTargetModel).where(RoleTargetModel.profile_id == profile.id)
    )
    scoring = session.get(ScoringPreferenceModel, profile.id)
    return Profile(
        display_name=profile.display_name,
        skills=skills,
        role_families=[RoleFamily(f.name, f.priority, f.enabled) for f in families],
        role_targets=[
            RoleTarget(
                t.title_pattern,
                list(t.include_keywords or []),
                list(t.exclude_keywords or []),
                list(t.target_seniority or []),
            )
            for t in targets
        ],
        search_preferences=_search_prefs(session.get(SearchPreferenceModel, profile.id)),
        scoring_preferences=ScoringPreferences(dict(scoring.weights or {})) if scoring else None,
    )
