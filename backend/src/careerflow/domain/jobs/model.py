"""Domain-level dataclass for job evaluation inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    title: str
    company: str
    description_text: str | None = None
    location_text: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_at: datetime | None = None
