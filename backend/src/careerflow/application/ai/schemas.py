"""Response schemas for AI tasks (validated with Pydantic; see plan section 11)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedItem(BaseModel):
    text: str = Field(min_length=1, max_length=200, description="normalised short form")
    source_quote: str = Field(default="", description="verbatim phrase from the job description")
    confidence: float = Field(default=0.8, ge=0, le=1)


class ExtractedRequirements(BaseModel):
    summary: str = ""
    responsibilities: list[ExtractedItem] = Field(default_factory=list)
    required_skills: list[ExtractedItem] = Field(default_factory=list)
    preferred_skills: list[ExtractedItem] = Field(default_factory=list)
    experience_requirements: list[ExtractedItem] = Field(default_factory=list)
    education_requirements: list[ExtractedItem] = Field(default_factory=list)
    leadership_expectations: list[ExtractedItem] = Field(default_factory=list)
    architecture_expectations: list[ExtractedItem] = Field(default_factory=list)
    management_expectations: list[ExtractedItem] = Field(default_factory=list)
    location_constraints: list[ExtractedItem] = Field(default_factory=list)
    travel_requirements: list[ExtractedItem] = Field(default_factory=list)
    potential_blockers: list[ExtractedItem] = Field(default_factory=list)
    ambiguous_requirements: list[ExtractedItem] = Field(default_factory=list)
    inferred_seniority: str | None = Field(
        default=None, description="one of entry, mid, senior, staff, principal, lead, manager, director, executive"
    )
