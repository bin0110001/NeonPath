from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RemoteType(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    TEMPORARY = "TEMPORARY"
    INTERNSHIP = "INTERNSHIP"


class SalaryPeriod(StrEnum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"


class JobFields(BaseModel):
    """Fields shared by create (required subset) and update (all optional)."""

    model_config = ConfigDict(use_enum_values=True)

    canonical_url: str | None = Field(default=None, max_length=500)
    company_domain: str | None = Field(default=None, max_length=100)
    description_html: str | None = None
    location_text: str | None = Field(default=None, max_length=200)
    remote_type: RemoteType | None = None
    employment_type: EmploymentType | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check_salary(self) -> "JobFields":
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must not exceed salary_max")
        return self


class JobCreate(JobFields):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    description_text: str = Field(min_length=1)
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)


class JobUpdate(JobFields):
    """Partial update: only fields present in the request body are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    description_text: str | None = Field(default=None, min_length=1)
    raw_metadata_json: dict[str, Any] | None = None


class JobOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str
    description_text: str
    canonical_url: str | None = None
    company_domain: str | None = None
    description_html: str | None = None
    location_text: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    discovered_at: datetime
    source_updated_at: datetime | None = None
    source_status: str | None = None
    fingerprint: str | None = None
    status: str
    raw_metadata_json: dict[str, Any] = Field(default_factory=dict)


class JobListItem(JobOutput):
    """A job as seen by one profile: its workflow status and latest evaluation summary."""

    workflow_status: str
    score: float | None = None
    has_blockers: bool | None = None


class DashboardOutput(BaseModel):
    profile_id: str
    total: int
    new_jobs: int
    needs_review: int
    high_fit: int
    shortlisted: int
    blocked: int
    unevaluated: int
    by_status: dict[str, int]


class JobSourceRecordCreate(BaseModel):
    adapter: str = Field(min_length=1, max_length=100)
    external_id: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class JobSourceRecordOutput(JobSourceRecordCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    discovered_at: datetime
    last_seen_at: datetime


class JobRequirementCreate(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    normalized_text: str = Field(min_length=1, max_length=200)
    source_text: str = Field(min_length=1)
    required_level: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)


class JobRequirementOutput(JobRequirementCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    extractor: str | None = None  # None = entered manually; "ai" or "keyword" = extracted
    provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None


class ExtractionOutput(BaseModel):
    mode: str  # "ai" or "keyword"
    summary: str = ""
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None
    requirements: list[JobRequirementOutput]


class JobImport(JobCreate):
    """Manual/fixture import: a job plus an optional source record and requirements."""

    source: JobSourceRecordCreate | None = None
    requirements: list[JobRequirementCreate] = Field(default_factory=list)


class JobEvaluationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    profile_id: str
    evaluator_version: str
    model_provider: str | None = None
    model_name: str | None = None
    overall_score: float
    confidence: float | None = None
    dimension_scores_json: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    transferable_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    explanation: str | None = None
    created_at: datetime


class EvaluateRequest(BaseModel):
    profile_id: str


class WorkflowActionRequest(BaseModel):
    profile_id: str
    actor: str | None = Field(default=None, max_length=100)
    reason: str | None = None


class WorkflowStatusOutput(BaseModel):
    job_id: str
    profile_id: str
    status: str


class StatusHistoryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    profile_id: str
    old_status: str | None = None
    new_status: str
    actor: str | None = None
    reason: str | None = None
    timestamp: datetime
