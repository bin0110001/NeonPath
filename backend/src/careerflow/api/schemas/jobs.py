from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobBase(BaseModel):
    canonical_url: str | None = None
    title: str
    company: str
    company_domain: str | None = None
    description_text: str
    description_html: str | None = None
    location_text: str | None = None
    remote_type: str | None = None  # REMOTE, HYBRID, ONSITE
    employment_type: str | None = None  # FULL_TIME, PART_TIME, CONTRACT, etc.
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None  # USD, EUR, etc.
    salary_period: str | None = None  # YEAR, MONTH, HOUR
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)


class JobCreate(JobBase):
    pass


class JobUpdate(JobBase):
    pass


class JobOutput(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    discovered_at: datetime
    source_updated_at: datetime | None = None
    source_status: str | None = None  # ACTIVE, EXPIRED, FILLED, etc.
    fingerprint: str | None = None  # For deduplication


class JobSourceRecordBase(BaseModel):
    adapter: str  # e.g., "manual", "rss", "greenhouse"
    external_id: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any]


class JobSourceRecordCreate(JobSourceRecordBase):
    pass


class JobSourceRecordOutput(JobSourceRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    discovered_at: datetime
    last_seen_at: datetime


class JobRequirementBase(BaseModel):
    type: str  # skill, experience, education, etc.
    normalized_text: str
    source_text: str
    required_level: str | None = None  # BEGINNER, INTERMEDIATE, EXPERT, etc.
    category: str | None = None  # Matches categories from spec
    confidence: float | None = None  # 0.0 to 1.0


class JobRequirementCreate(JobRequirementBase):
    pass


class JobRequirementOutput(JobRequirementBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str


class JobEvaluationBase(BaseModel):
    evaluator_version: str
    model_provider: str | None = None
    model_name: str | None = None
    overall_score: float  # 0.0 to 1.0
    confidence: float | None = None
    dimension_scores_json: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    transferable_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    explanation: str | None = None


class JobEvaluationCreate(JobEvaluationBase):
    profile_id: str  # Required for creating an evaluation


class JobEvaluationOutput(JobEvaluationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    profile_id: str
    created_at: datetime