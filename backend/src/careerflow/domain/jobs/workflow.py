"""Profile-scoped review/application workflow (plan section 8, "User workflow").

Pure domain logic: no FastAPI or SQLAlchemy imports. The processing lifecycle
(DISCOVERED ... READY_FOR_REVIEW) lives on the job; this state machine is what a
single profile does with that job afterwards.
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowStatus(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    SHORTLISTED = "SHORTLISTED"
    SAVED = "SAVED"
    ARCHIVED = "ARCHIVED"
    PREPARING = "PREPARING"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    SCREENING = "SCREENING"
    INTERVIEWING = "INTERVIEWING"
    FINAL = "FINAL"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


S = WorkflowStatus

INITIAL_STATUS = S.READY_FOR_REVIEW

ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    S.READY_FOR_REVIEW: frozenset({S.SHORTLISTED, S.REJECTED, S.SAVED, S.ARCHIVED}),
    S.SAVED: frozenset({S.SHORTLISTED, S.REJECTED, S.ARCHIVED}),
    S.SHORTLISTED: frozenset({S.PREPARING, S.SAVED, S.REJECTED, S.ARCHIVED}),
    S.PREPARING: frozenset({S.READY_TO_APPLY, S.REJECTED, S.ARCHIVED}),
    S.READY_TO_APPLY: frozenset({S.APPLIED, S.PREPARING, S.REJECTED, S.ARCHIVED}),
    S.APPLIED: frozenset({S.SCREENING, S.REJECTED, S.WITHDRAWN}),
    S.SCREENING: frozenset({S.INTERVIEWING, S.REJECTED, S.WITHDRAWN}),
    S.INTERVIEWING: frozenset({S.FINAL, S.REJECTED, S.WITHDRAWN}),
    S.FINAL: frozenset({S.OFFER, S.REJECTED, S.WITHDRAWN}),
    # Reopening a decision sends the job back to review; everything else is terminal.
    S.REJECTED: frozenset({S.READY_FOR_REVIEW}),
    S.ARCHIVED: frozenset({S.READY_FOR_REVIEW}),
    S.OFFER: frozenset(),
    S.WITHDRAWN: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, old: WorkflowStatus, new: WorkflowStatus) -> None:
        self.old = old
        self.new = new
        super().__init__(f"Transition {old.value} -> {new.value} is not allowed")


def parse_status(value: str) -> WorkflowStatus:
    try:
        return WorkflowStatus(value)
    except ValueError as error:
        raise ValueError(f"Unknown workflow status: {value}") from error


def validate_transition(old: WorkflowStatus, new: WorkflowStatus) -> None:
    """Raise InvalidTransitionError unless old -> new is allowed (same-status is not)."""
    if new not in ALLOWED_TRANSITIONS[old]:
        raise InvalidTransitionError(old, new)
