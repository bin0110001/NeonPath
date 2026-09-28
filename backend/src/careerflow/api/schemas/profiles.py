from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProfileInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    display_name: str
    headline: str | None = None
    summary: str | None = None
    timezone: str = "UTC"
    status: str = "active"


class ProfileOutput(ProfileInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class ContactInput(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None


class ContactOutput(ContactInput):
    model_config = ConfigDict(from_attributes=True)
    profile_id: str


class ExperienceInput(BaseModel):
    organization: str
    title: str
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None
    employment_type: str | None = None
    location: str | None = None
    sort_order: int = 0


class ExperienceOutput(ExperienceInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str


class AchievementInput(BaseModel):
    experience_id: str | None = None
    title: str
    situation: str | None = None
    action: str | None = None
    result: str | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    technologies: list[str] = Field(default_factory=list)
    competency_tags: list[str] = Field(default_factory=list)
    verified: bool = False


class AchievementOutput(AchievementInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str


class SkillInput(BaseModel):
    canonical_name: str
    category: str | None = None
    proficiency: str | None = None
    years_experience: float | None = None
    last_used_year: int | None = None
    evidence_notes: str | None = None
    verified: bool = False
    aliases: list[str] = Field(default_factory=list)


class SkillOutput(SkillInput):
    profile_id: str


class EducationInput(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class EducationOutput(EducationInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str


class PortfolioInput(BaseModel):
    name: str
    description: str | None = None
    url: str | None = None
    technologies: list[str] = Field(default_factory=list)
    verified: bool = False


class PortfolioOutput(PortfolioInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str


class RoleFamilyInput(BaseModel):
    name: str
    priority: int = 0
    enabled: bool = True


class RoleFamilyOutput(RoleFamilyInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str


class SearchPreferenceInput(BaseModel):
    remote_preference: str = "NEUTRAL"
    allowed_countries: list[str] = Field(default_factory=list)
    allowed_regions: list[str] = Field(default_factory=list)
    allowed_cities: list[str] = Field(default_factory=list)
    relocation_allowed: bool = False
    travel_percentage_max: int | None = None
    employment_types: list[str] = Field(default_factory=list)
    minimum_base_salary: int | None = None
    minimum_total_comp: int | None = None
    currency: str | None = None
    excluded_companies: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    excluded_industries: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)


class SearchPreferenceOutput(SearchPreferenceInput):
    model_config = ConfigDict(from_attributes=True)
    profile_id: str


class ScoringPreferenceInput(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)


class ScoringPreferenceOutput(ScoringPreferenceInput):
    model_config = ConfigDict(from_attributes=True)
    profile_id: str


class ProfileExport(BaseModel):
    schema_version: int = 1
    profile: ProfileInput
    contact: ContactInput | None = None
    experiences: list[ExperienceInput] = Field(default_factory=list)
    achievements: list[AchievementInput] = Field(default_factory=list)
