"""Domain-level dataclasses for profile-related evaluation inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoleFamily:
    name: str
    priority: int = 0
    enabled: bool = True


@dataclass
class RoleTarget:
    title_pattern: str | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    target_seniority: list[str] = field(default_factory=list)


@dataclass
class SearchPreferences:
    remote_preference: str = "NEUTRAL"
    allowed_countries: list[str] = field(default_factory=list)
    allowed_regions: list[str] = field(default_factory=list)
    allowed_cities: list[str] = field(default_factory=list)
    excluded_countries: list[str] = field(default_factory=list)
    excluded_regions: list[str] = field(default_factory=list)
    excluded_cities: list[str] = field(default_factory=list)
    relocation_allowed: bool = False
    minimum_base_salary: int | None = None
    minimum_total_comp: int | None = None
    currency: str | None = None
    excluded_employment_types: list[str] = field(default_factory=list)
    preferred_employment_types: list[str] = field(default_factory=list)


@dataclass
class ScoringPreferences:
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class Profile:
    display_name: str
    skills: list[Any] = field(default_factory=list)
    role_families: list[RoleFamily] = field(default_factory=list)
    role_targets: list[RoleTarget] = field(default_factory=list)
    search_preferences: SearchPreferences | None = None
    scoring_preferences: ScoringPreferences | None = None
