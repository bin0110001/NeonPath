"""Fictional demo data. Idempotent: running it repeatedly never duplicates rows.

Run with ``python -m careerflow.seed``. All names, companies and numbers are invented.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import (
    AchievementModel,
    ExperienceModel,
    JobModel,
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
from careerflow.infrastructure.database.session import create_database_engine

# canonical name -> (category, aliases)
SKILLS: dict[str, tuple[str, list[str]]] = {
    "Python": ("language", []),
    "C#": ("language", ["C Sharp"]),
    "SQL": ("language", []),
    "LLM": ("ai", ["Large Language Models", "GenAI"]),
    "Machine Learning": ("ai", ["ML"]),
    "Distributed Systems": ("architecture", []),
    "Cloud Architecture": ("architecture", []),
    "Azure": ("cloud", []),
    "AWS": ("cloud", ["Amazon Web Services"]),
    "Experimentation": ("analytics", ["A/B testing"]),
    "Forecasting": ("analytics", []),
    "Tableau": ("visualization", []),
}

PROFILES: list[dict[str, Any]] = [
    {
        "slug": "jordan-lee",
        "display_name": "Jordan Lee",
        "headline": "Principal Software / AI Engineer",
        "summary": "Fictional demo profile for platform architecture and applied AI roles.",
        "timezone": "America/New_York",
        "experience": ("Northstar Systems", "Principal Engineer", "Led cloud platforms, distributed systems, and LLM applications."),
        "achievement": ("Production AI platform", "Designed a governed LLM application platform for product teams.", ["Python", "C#", "Cloud architecture", "LLM applications"]),
        "skills": [("Python", 12), ("C#", 10), ("LLM", 3), ("Distributed Systems", 10), ("Cloud Architecture", 8), ("Azure", 6)],
        "families": ["AI Engineer", "Software Architect"],
        "targets": [("principal*engineer", ["ai", "platform"], ["intern"], ["principal", "staff"])],
        "prefs": {
            "remote_preference": "REQUIRED",
            "minimum_base_salary": 170000,
            "currency": "USD",
            "employment_types": ["FULL_TIME"],
            "excluded_companies": ["Smokestack Tobacco"],
            "preferred_industries": ["Software"],
        },
        "weights": {"role_alignment": 0.3, "seniority_alignment": 0.2, "technical_alignment": 0.25, "location_alignment": 0.15, "compensation_alignment": 0.1},
    },
    {
        "slug": "morgan-rivera",
        "display_name": "Morgan Rivera",
        "headline": "Senior Data Scientist",
        "summary": "Fictional demo profile for analytics, experimentation, and forecasting roles.",
        "timezone": "America/Chicago",
        "experience": ("Cedar Analytics", "Senior Data Scientist", "Built forecasting and experimentation products using Python and SQL."),
        "achievement": ("Forecasting program", "Improved demand forecasting through experiment design and ML modeling.", ["Python", "SQL", "Machine learning", "Visualization"]),
        "skills": [("Python", 8), ("SQL", 8), ("Machine Learning", 6), ("Experimentation", 6), ("Forecasting", 5), ("Tableau", 4), ("AWS", 3)],
        "families": ["Data Scientist", "Analytics Lead"],
        "targets": [("data scientist", ["analytics", "forecasting"], ["intern"], ["senior"])],
        "prefs": {
            "remote_preference": "PREFERRED",
            "allowed_cities": ["Chicago"],
            "allowed_countries": ["United States"],
            "minimum_base_salary": 120000,
            "currency": "USD",
            "preferred_industries": ["Retail", "Healthcare"],
        },
        "weights": {"role_alignment": 0.25, "seniority_alignment": 0.15, "technical_alignment": 0.3, "location_alignment": 0.15, "compensation_alignment": 0.15},
    },
]

_COMMON = {"employment_type": "FULL_TIME", "salary_currency": "USD", "salary_period": "YEAR"}

JOBS: list[dict[str, Any]] = [
    {  # strong for Jordan, weak for Morgan
        "title": "Principal AI Platform Engineer", "company": "Lumen Robotics",
        "description_text": "Lead our LLM application platform. Python, C#, Azure and distributed systems at scale.",
        "location_text": "Remote, United States", "remote_type": "REMOTE",
        "salary_min": 190000, "salary_max": 240000, "raw_metadata_json": {"industry": "Software"},
        "canonical_url": "https://example.com/demo/lumen-principal-ai", **_COMMON,
    },
    {  # strong for Morgan, weak for Jordan
        "title": "Senior Data Scientist, Forecasting", "company": "Harbor Retail Group",
        "description_text": "Own demand forecasting and experimentation. Python, SQL, machine learning and Tableau.",
        "location_text": "Chicago, Illinois, United States", "remote_type": "HYBRID",
        "salary_min": 135000, "salary_max": 165000, "raw_metadata_json": {"industry": "Retail"},
        "canonical_url": "https://example.com/demo/harbor-senior-ds", **_COMMON,
    },
    {  # blocked for Jordan: onsite (remote required) and excluded company
        "title": "Principal Platform Engineer", "company": "Smokestack Tobacco",
        "description_text": "On-site platform engineering with Python and distributed systems.",
        "location_text": "Louisville, Kentucky, United States", "remote_type": "ONSITE",
        "salary_min": 180000, "salary_max": 210000, "raw_metadata_json": {"industry": "Tobacco"},
        "canonical_url": "https://example.com/demo/smokestack-principal", **_COMMON,
    },
    {  # transferable for Morgan: wants a cloud skill she lacks in exact form (Azure) but holds AWS
        "title": "Senior Data Scientist", "company": "Blue Meridian Health",
        "description_text": "Build clinical forecasting models in Python and SQL, deployed on Azure.",
        "location_text": "Remote, United States", "remote_type": "REMOTE",
        "salary_min": 125000, "salary_max": 150000, "raw_metadata_json": {"industry": "Healthcare"},
        "canonical_url": "https://example.com/demo/blue-meridian-ds", **_COMMON,
    },
]


def _get_or_create_skills(session: Session) -> dict[str, SkillModel]:
    out: dict[str, SkillModel] = {}
    for name, (category, aliases) in SKILLS.items():
        skill = session.scalar(select(SkillModel).where(SkillModel.canonical_name == name))
        if skill is None:
            skill = SkillModel(canonical_name=name, category=category)
            session.add(skill)
            session.flush()
        for alias in aliases:
            if session.get(SkillAliasModel, alias) is None:
                session.add(SkillAliasModel(alias=alias, skill_id=skill.id))
        out[name] = skill
    return out


def _seed_profile(session: Session, spec: dict[str, Any], skills: dict[str, SkillModel]) -> None:
    if session.scalar(select(ProfileModel.id).where(ProfileModel.slug == spec["slug"])):
        return
    profile = ProfileModel(
        slug=spec["slug"], display_name=spec["display_name"], headline=spec["headline"],
        summary=spec["summary"], timezone=spec["timezone"],
    )  # fmt: skip
    session.add(profile)
    session.flush()
    org, title, description = spec["experience"]
    ach_title, ach_action, ach_tech = spec["achievement"]
    session.add_all(
        [
            ProfileContactModel(profile_id=profile.id, full_name=spec["display_name"]),
            ExperienceModel(profile_id=profile.id, organization=org, title=title, description=description),
            AchievementModel(profile_id=profile.id, title=ach_title, action=ach_action, technologies=ach_tech, verified=True),
            ScoringPreferenceModel(profile_id=profile.id, weights=spec["weights"]),
            SearchPreferenceModel(profile_id=profile.id, **spec["prefs"]),
        ]
    )  # fmt: skip
    for name, years in spec["skills"]:
        session.add(ProfileSkillModel(profile_id=profile.id, skill_id=skills[name].id, years_experience=years, verified=True))
    for priority, family in enumerate(spec["families"]):
        session.add(RoleFamilyModel(profile_id=profile.id, name=family, priority=priority))
    for pattern, include, exclude, seniority in spec["targets"]:
        session.add(
            RoleTargetModel(
                profile_id=profile.id, title_pattern=pattern, include_keywords=include,
                exclude_keywords=exclude, target_seniority=seniority,
            )  # fmt: skip
        )


def seed_session(session: Session) -> None:
    skills = _get_or_create_skills(session)
    for spec in PROFILES:
        _seed_profile(session, spec, skills)
    for job in JOBS:
        exists = session.scalar(
            select(JobModel.id).where(
                JobModel.title == job["title"], JobModel.company == job["company"]
            )
        )
        if exists is None:
            session.add(JobModel(status="READY_FOR_REVIEW", **job))
    session.commit()


def seed_demo_data() -> None:
    """Create safe, fictional demo data; never overwrites or duplicates existing rows."""
    with Session(create_database_engine()) as session:
        seed_session(session)


if __name__ == "__main__":
    seed_demo_data()
