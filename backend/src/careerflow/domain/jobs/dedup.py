"""Duplicate detection between two postings (plan section 10). Pure logic, no frameworks.

Classification: EXACT (same fingerprint), LIKELY, POSSIBLE, DISTINCT. A company mismatch
is always DISTINCT: two different employers never "probably" share an opening.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from careerflow.domain.jobs.fingerprint import (
    job_fingerprint,
    normalize_company,
    normalize_location,
    normalize_title,
)

EXACT, LIKELY, POSSIBLE, DISTINCT = "EXACT", "LIKELY", "POSSIBLE", "DISTINCT"
LIKELY_THRESHOLD = 0.85
POSSIBLE_THRESHOLD = 0.60
MAX_POSTED_GAP_DAYS = 30

WEIGHTS = {"title": 0.35, "description": 0.30, "location": 0.15, "salary": 0.10, "posted": 0.10}


@dataclass(frozen=True)
class JobSignature:
    company: str
    title: str
    location: str | None = None
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    posted_at: datetime | None = None
    requisition_id: str | None = None

    @property
    def fingerprint(self) -> str:
        return job_fingerprint(self.company, self.title, self.location)


@dataclass(frozen=True)
class MatchResult:
    classification: str
    score: float
    reasons: list[str] = field(default_factory=list)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _words(text: str | None, limit: int = 400) -> set[str]:
    return set(re.findall(r"[a-z0-9+#]{3,}", (text or "").lower())[:limit])


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _salary_overlap(a: JobSignature, b: JobSignature) -> float | None:
    if None in (a.salary_min, a.salary_max, b.salary_min, b.salary_max):
        return None
    low, high = max(a.salary_min or 0, b.salary_min or 0), min(a.salary_max or 0, b.salary_max or 0)
    span = max(a.salary_max or 0, b.salary_max or 0) - min(a.salary_min or 0, b.salary_min or 0)
    return 1.0 if span <= 0 and low == high else max(0.0, (high - low) / span) if span > 0 else 0.0


def match(a: JobSignature, b: JobSignature) -> MatchResult:
    if normalize_company(a.company) != normalize_company(b.company):
        return MatchResult(DISTINCT, 0.0, ["different company"])
    reasons = ["same company"]
    if a.requisition_id and a.requisition_id == b.requisition_id:
        return MatchResult(EXACT, 1.0, [*reasons, f"same requisition id {a.requisition_id}"])
    if a.fingerprint == b.fingerprint:
        return MatchResult(EXACT, 1.0, [*reasons, "same title and location"])

    scores: dict[str, float | None] = {
        "title": _similarity(normalize_title(a.title), normalize_title(b.title)),
        "description": _jaccard(_words(a.description), _words(b.description)),
        "location": (
            _similarity(normalize_location(a.location), normalize_location(b.location))
            if a.location and b.location
            else None
        ),
        "salary": _salary_overlap(a, b),
        "posted": None,
    }
    if a.posted_at and b.posted_at:
        gap = abs((a.posted_at - b.posted_at).days)
        scores["posted"] = max(0.0, 1 - gap / MAX_POSTED_GAP_DAYS)

    known = {k: v for k, v in scores.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in known)
    score = sum(WEIGHTS[k] * v for k, v in known.items()) / total_weight if total_weight else 0.0
    for key, value in known.items():
        if value >= 0.8:
            reasons.append(f"similar {key} ({value:.0%})")
        elif value < 0.4:
            reasons.append(f"different {key} ({value:.0%})")

    # a clearly different title cannot be rescued by matching boilerplate text
    if scores["title"] is not None and scores["title"] < 0.5:
        score = min(score, POSSIBLE_THRESHOLD - 0.01)
    classification = LIKELY if score >= LIKELY_THRESHOLD else POSSIBLE if score >= POSSIBLE_THRESHOLD else DISTINCT
    return MatchResult(classification, round(score, 3), reasons)
