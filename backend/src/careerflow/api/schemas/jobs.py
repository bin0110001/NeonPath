from datetime date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobBase(BaseModel):
    canonical_url: Optional[str] = None
    title: str
    company: str
    company_domain: Optional[str] = None
    description_text: str
    description_html: Optional[str] = None
    location_text: Optional[str] = None
    remote_type: Optional[str] = None  # REMOTE, HYBRID, ONSITE
    employment_type: Optional[str] = None  # FULL_TIME, PART_TIME, CONTRACT, etc.
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None  # USD, EUR, etc.
    salary_period: Optional[str] = None  # YEAR, MONTH, HOUR
    posted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)


class JobCreate(JobBase):
    pass


class JobUpdate(JobBase):
    pass


class JobOutput(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    discovered_at: datetime
    source_updated_at: Optional[datetime] = None
    source_status: Optional[str] = None  # ACTIVE, EXPIRED, FILLED, etc.
    fingerprint: Optional[str] = None  # For deduplication


class JobSourceRecordBase(BaseModel):
    adapter: str  # e.g., "manual", "rss", "greenhouse"
    external_id: Optional[str] = None
    source_url: Optional[str] = None
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
    required_level: Optional[str] = None  # BEGINNER, INTERMEDIATE, EXPERT, etc.
    category: Optional[str] = None  # Matches categories from spec
    confidence: Optional[float] = None  # 0.0 to 1.0


class JobRequirementCreate(JobRequirementBase):
    pass


class JobRequirementOutput(JobRequirementBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str


class JobEvaluationBase(BaseModel):
    evaluator_version: str
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    overall_score: float  # 0.0 to 1.0
    confidence: Optional[float] = None
    dimension_scores_json: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    transferable_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    explanation: Optional[str] = None


class JobEvaluationCreate(JobEvaluationBase):
    profile_id: str  # Required for creating an evaluation


class JobEvaluationOutput(JobEvaluationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    profile_id: str
    created_at: datetime