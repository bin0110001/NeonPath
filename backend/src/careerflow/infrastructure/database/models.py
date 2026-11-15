from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Root metadata for future infrastructure-owned ORM models."""


def new_id() -> str:
    return str(uuid.uuid4())


class ProfileModel(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    contact: Mapped[ProfileContactModel | None] = relationship(back_populates="profile")
    experiences: Mapped[list[ExperienceModel]] = relationship(back_populates="profile")


class ProfileContactModel(Base):
    __tablename__ = "profile_contacts"

    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    profile: Mapped[ProfileModel] = relationship(back_populates="contact")


class ExperienceModel(Base):
    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    organization: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[ProfileModel] = relationship(back_populates="experiences")


class AchievementModel(Base):
    __tablename__ = "achievements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    experience_id: Mapped[str | None] = mapped_column(ForeignKey("experiences.id"))
    title: Mapped[str] = mapped_column(String(300))
    situation: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    competency_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class SkillModel(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str | None] = mapped_column(String(100))


class SkillAliasModel(Base):
    __tablename__ = "skill_aliases"

    alias: Mapped[str] = mapped_column(String(200), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)


class ProfileSkillModel(Base):
    __tablename__ = "profile_skills"

    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    proficiency: Mapped[str | None] = mapped_column(String(50))
    years_experience: Mapped[float | None] = mapped_column(Float)
    last_used_year: Mapped[int | None] = mapped_column(Integer)
    evidence_notes: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class EducationModel(Base):
    __tablename__ = "education"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    institution: Mapped[str] = mapped_column(String(250))
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class PortfolioItemModel(Base):
    __tablename__ = "portfolio_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class RoleFamilyModel(Base):
    __tablename__ = "role_families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RoleTargetModel(Base):
    __tablename__ = "role_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    title_pattern: Mapped[str | None] = mapped_column(String(200))
    include_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_seniority: Mapped[list[str]] = mapped_column(JSON, default=list)


class SearchPreferenceModel(Base):
    __tablename__ = "search_preferences"

    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    remote_preference: Mapped[str] = mapped_column(String(32), default="NEUTRAL")
    allowed_countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_cities: Mapped[list[str]] = mapped_column(JSON, default=list)
    relocation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    travel_percentage_max: Mapped[int | None] = mapped_column(Integer)
    employment_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_base_salary: Mapped[int | None] = mapped_column(Integer)
    minimum_total_comp: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    excluded_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_industries: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_industries: Mapped[list[str]] = mapped_column(JSON, default=list)


class ScoringPreferenceModel(Base):
    __tablename__ = "scoring_preferences"

    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)


# Job-related models
class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))
    company_domain: Mapped[str | None] = mapped_column(String(100))
    description_text: Mapped[str] = mapped_column(Text)
    description_html: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(String(200))
    remote_type: Mapped[str | None] = mapped_column(String(32))  # REMOTE, HYBRID, ONSITE
    employment_type: Mapped[str | None] = mapped_column(String(64))  # FULL_TIME, PART_TIME, CONTRACT, etc.
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(3))  # USD, EUR, etc.
    salary_period: Mapped[str | None] = mapped_column(String(20))  # YEAR, MONTH, HOUR
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str | None] = mapped_column(String(32))  # ACTIVE, EXPIRED, FILLED, etc.
    fingerprint: Mapped[str | None] = mapped_column(String(64))  # For deduplication
    raw_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Workflow status
    status: Mapped[str] = mapped_column(String(32), default="DISCOVERED")  # DISCOVERED, INGESTED, NORMALIZED, DEDUPLICATED, ENRICHED, EVALUATED, READY_FOR_REVIEW, SHORTLISTED, REJECTED, SAVED, ARCHIVED

    # Relationships
    source_records: Mapped[list[JobSourceRecordModel]] = relationship(back_populates="job", cascade="all, delete-orphan")
    requirements: Mapped[list[JobRequirementModel]] = relationship(back_populates="job", cascade="all, delete-orphan")
    evaluations: Mapped[list[JobEvaluationModel]] = relationship(back_populates="job", cascade="all, delete-orphan")
    status_history: Mapped[list[JobStatusHistoryModel]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobSourceRecordModel(Base):
    __tablename__ = "job_source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    adapter: Mapped[str] = mapped_column(String(100))  # e.g., "manual", "rss", "greenhouse"
    external_id: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    job: Mapped[JobModel] = relationship(back_populates="source_records")


class JobRequirementModel(Base):
    __tablename__ = "job_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # skill, experience, education, etc.
    normalized_text: Mapped[str] = mapped_column(String(200))
    source_text: Mapped[str] = mapped_column(Text)
    required_level: Mapped[str | None] = mapped_column(String(50))  # BEGINNER, INTERMEDIATE, EXPERT, etc.
    category: Mapped[str | None] = mapped_column(String(100))  # Matches categories from spec
    confidence: Mapped[float | None] = mapped_column(Float)  # 0.0 to 1.0

    # Relationships
    job: Mapped[JobModel] = relationship(back_populates="requirements")


class JobEvaluationModel(Base):
    __tablename__ = "job_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    evaluator_version: Mapped[str] = mapped_column(String(50))
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(100))
    overall_score: Mapped[float] = mapped_column(Float)  # 0.0 to 1.0
    confidence: Mapped[float | None] = mapped_column(Float)
    dimension_scores_json: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    transferable_matches: Mapped[list[str]] = mapped_column(JSON, default=list)
    gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers: Mapped[list[str]] = mapped_column(JSON, default=list)
    unknowns: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job: Mapped[JobModel] = relationship(back_populates="evaluations")


class JobStatusHistoryModel(Base):
    __tablename__ = "job_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str | None] = mapped_column(String(100))  # user, system, etc.
    reason: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job: Mapped[JobModel] = relationship(back_populates="status_history")
