"""Search funnel metrics from workflow history (plan section 31, Phase 10). Pure logic.

Everything is derived from one profile's status-history events, so the numbers can always
be explained by (and reproduced from) the recorded transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median


@dataclass(frozen=True)
class Transition:
    job_id: str
    old_status: str | None
    new_status: str
    at: datetime


@dataclass(frozen=True)
class FunnelMetrics:
    jobs_reviewed: int  # jobs the user made a first decision on
    shortlisted: int
    applications_submitted: int
    screens: int
    interviews: int
    final_interviews: int
    offers: int
    responded: int  # applications that got any answer (screen, interview, final, offer or rejection)
    response_rate: float | None  # responded / applications_submitted
    median_days_to_response: float | None
    average_days_to_response: float | None


RESPONSE_STATUSES = frozenset({"SCREENING", "INTERVIEWING", "FINAL", "OFFER", "REJECTED"})


def _ever(events: list[Transition], status: str) -> set[str]:
    return {t.job_id for t in events if t.new_status == status}


def compute_metrics(events: list[Transition]) -> FunnelMetrics:
    ordered = sorted(events, key=lambda t: t.at)
    reviewed = {t.job_id for t in ordered if t.old_status == "READY_FOR_REVIEW"}
    applied_at: dict[str, datetime] = {}
    for t in ordered:
        if t.new_status == "APPLIED":
            applied_at.setdefault(t.job_id, t.at)

    responded: dict[str, datetime] = {}
    for t in ordered:
        if t.job_id in applied_at and t.new_status in RESPONSE_STATUSES and t.at >= applied_at[t.job_id]:
            responded.setdefault(t.job_id, t.at)
    days = [(responded[j] - applied_at[j]).total_seconds() / 86400 for j in responded]

    applied = len(applied_at)
    return FunnelMetrics(
        jobs_reviewed=len(reviewed),
        shortlisted=len(_ever(ordered, "SHORTLISTED")),
        applications_submitted=applied,
        screens=len(_ever(ordered, "SCREENING")),
        interviews=len(_ever(ordered, "INTERVIEWING")),
        final_interviews=len(_ever(ordered, "FINAL")),
        offers=len(_ever(ordered, "OFFER")),
        responded=len(responded),
        response_rate=round(len(responded) / applied, 4) if applied else None,
        median_days_to_response=round(median(days), 2) if days else None,
        average_days_to_response=round(sum(days) / len(days), 2) if days else None,
    )
