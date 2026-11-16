import pytest

from careerflow.domain.jobs.workflow import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    WorkflowStatus,
    parse_status,
    validate_transition,
)

S = WorkflowStatus


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (S.READY_FOR_REVIEW, S.SHORTLISTED),
        (S.READY_FOR_REVIEW, S.REJECTED),
        (S.READY_FOR_REVIEW, S.SAVED),
        (S.READY_FOR_REVIEW, S.ARCHIVED),
        (S.SHORTLISTED, S.PREPARING),
        (S.PREPARING, S.READY_TO_APPLY),
        (S.READY_TO_APPLY, S.APPLIED),
        (S.APPLIED, S.SCREENING),
        (S.SCREENING, S.INTERVIEWING),
        (S.INTERVIEWING, S.FINAL),
        (S.FINAL, S.OFFER),
        (S.FINAL, S.WITHDRAWN),
        (S.REJECTED, S.READY_FOR_REVIEW),
    ],
)
def test_allowed_transitions(old: WorkflowStatus, new: WorkflowStatus) -> None:
    validate_transition(old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (S.REJECTED, S.APPLIED),
        (S.READY_FOR_REVIEW, S.APPLIED),
        (S.SHORTLISTED, S.OFFER),
        (S.OFFER, S.REJECTED),
        (S.WITHDRAWN, S.APPLIED),
        (S.SAVED, S.SAVED),
        (S.APPLIED, S.SHORTLISTED),
    ],
)
def test_forbidden_transitions(old: WorkflowStatus, new: WorkflowStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        validate_transition(old, new)


def test_every_status_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(WorkflowStatus)


def test_parse_status_rejects_unknown() -> None:
    assert parse_status("SAVED") is S.SAVED
    with pytest.raises(ValueError, match="Unknown workflow status"):
        parse_status("NOPE")
