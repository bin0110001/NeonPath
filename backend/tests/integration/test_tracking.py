from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.tracking import get_session as tracking_session
from careerflow.domain.applications.metrics import Transition, compute_metrics
from careerflow.infrastructure.database.models import Base, JobModel, JobStatusHistoryModel
from careerflow.main import create_app

API = "/api/v1"
NOW = datetime.now(UTC)


# --- metrics (pure) -------------------------------------------------------------------------------


def day(n: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=n)


def test_metrics_match_a_hand_computed_fixture() -> None:
    t = Transition
    events = [
        # job A: reviewed, shortlisted, applied day 2, screen day 5, interview day 9
        t("A", "READY_FOR_REVIEW", "SHORTLISTED", day(0)), t("A", "SHORTLISTED", "APPLIED", day(2)),
        t("A", "APPLIED", "SCREENING", day(5)), t("A", "SCREENING", "INTERVIEWING", day(9)),
        # job B: applied day 3, rejected day 4  -> a response after 1 day
        t("B", "READY_FOR_REVIEW", "SHORTLISTED", day(0)), t("B", "SHORTLISTED", "APPLIED", day(3)),
        t("B", "APPLIED", "REJECTED", day(4)),
        # job C: applied day 10, never answered
        t("C", "READY_FOR_REVIEW", "SHORTLISTED", day(1)), t("C", "SHORTLISTED", "APPLIED", day(10)),
        # job D: rejected straight from review (no application)
        t("D", "READY_FOR_REVIEW", "REJECTED", day(1)),
        # job E: reached final and an offer
        t("E", "READY_FOR_REVIEW", "SAVED", day(0)), t("E", "SAVED", "SHORTLISTED", day(1)),
        t("E", "SHORTLISTED", "APPLIED", day(1)), t("E", "APPLIED", "SCREENING", day(2)),
        t("E", "SCREENING", "INTERVIEWING", day(3)), t("E", "INTERVIEWING", "FINAL", day(4)),
        t("E", "FINAL", "OFFER", day(5)),
    ]  # fmt: skip
    m = compute_metrics(events)
    assert (m.jobs_reviewed, m.shortlisted, m.applications_submitted) == (5, 4, 4)
    assert (m.screens, m.interviews, m.final_interviews, m.offers) == (2, 2, 1, 1)
    assert m.responded == 3  # A, B (rejection) and E; C never answered; D never applied
    assert m.response_rate == 0.75
    # days to first response: A 3, B 1, E 1  -> median 1, average 1.67
    assert m.median_days_to_response == 1.0 and m.average_days_to_response == pytest.approx(1.67, abs=0.01)


def test_metrics_with_no_data_have_no_rates() -> None:
    m = compute_metrics([])
    assert (m.applications_submitted, m.response_rate, m.median_days_to_response) == (0, None, None)


def test_a_rejection_before_applying_is_not_a_response() -> None:
    m = compute_metrics([Transition("X", "SHORTLISTED", "REJECTED", day(1)), Transition("X", "READY_FOR_REVIEW", "SHORTLISTED", day(0))])
    assert m.applications_submitted == 0 and m.responded == 0


# --- API -----------------------------------------------------------------------------------------------


@pytest.fixture
def env() -> Generator[tuple[TestClient, Session]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    app = create_app()
    for dep in (profiles_session, tracking_session):
        app.dependency_overrides[dep] = lambda: session
    yield TestClient(app), session
    session.close()


def mk_profile(client: TestClient, slug: str) -> str:
    return str(client.post(f"{API}/profiles", json={"slug": slug, "display_name": slug}).json()["id"])


def mk_job(session: Session, title: str = "Engineer") -> str:
    job = JobModel(title=title, company="Contoso", description_text="d", status="READY_FOR_REVIEW")
    session.add(job)
    session.commit()
    return job.id


def move(client: TestClient, profile: str, job: str, *path: str) -> None:
    for to in path:
        r = client.post(f"{API}/jobs/{job}/transition", json={"profile_id": profile, "to_status": to})
        assert r.status_code == 200, (to, r.text)


def to_applied(client: TestClient, profile: str, job: str) -> None:
    move(client, profile, job, "SHORTLISTED", "PREPARING", "READY_TO_APPLY", "APPLIED")


def test_pipeline_moves_are_validated_transitions_with_history(env: tuple[TestClient, Session]) -> None:
    client, session = env
    p, job = mk_profile(client, "a"), mk_job(session)
    move(client, p, job, "SHORTLISTED")
    illegal = client.post(f"{API}/jobs/{job}/transition", json={"profile_id": p, "to_status": "OFFER"})
    assert illegal.status_code == 409
    assert client.post(f"{API}/jobs/{job}/transition", json={"profile_id": p, "to_status": "BOGUS"}).status_code == 422
    assert client.post(f"{API}/jobs/{job}/transition", json={"profile_id": p, "to_status": "SHORTLISTED"}).status_code == 409
    rows = list(session.scalars(select(JobStatusHistoryModel).where(JobStatusHistoryModel.profile_id == p)))
    assert [(r.old_status, r.new_status) for r in rows] == [("READY_FOR_REVIEW", "SHORTLISTED")]  # failures wrote nothing
    assert client.post(f"{API}/jobs/nope/transition", json={"profile_id": p, "to_status": "SAVED"}).status_code == 404


def test_pipeline_board_columns_cards_and_profile_scoping(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = mk_profile(client, "a"), mk_profile(client, "b")
    job1, job2 = mk_job(session, "One"), mk_job(session, "Two")
    move(client, a, job1, "SHORTLISTED", "PREPARING")
    to_applied(client, a, job2)
    move(client, b, job1, "SHORTLISTED")
    board = client.get(f"{API}/profiles/{a}/pipeline").json()["columns"]
    assert [c["title"] for c in board["PREPARING"]] == ["One"] and [c["title"] for c in board["APPLIED"]] == ["Two"]
    assert board["SHORTLISTED"] == [] and "READY_FOR_REVIEW" not in board
    assert [c["status"] for c in client.get(f"{API}/profiles/{b}/pipeline").json()["columns"]["SHORTLISTED"]] == ["SHORTLISTED"]
    assert client.get(f"{API}/profiles/{b}/pipeline").json()["columns"]["APPLIED"] == []
    assert client.get(f"{API}/profiles/nope/pipeline").status_code == 404


def test_entering_applied_creates_the_application_record(env: tuple[TestClient, Session]) -> None:
    client, session = env
    p, job = mk_profile(client, "a"), mk_job(session)
    to_applied(client, p, job)
    apps = client.get(f"{API}/profiles/{p}/applications").json()
    assert len(apps) == 1 and apps[0]["job_id"] == job and apps[0]["applied_at"] is not None
    card = client.get(f"{API}/profiles/{p}/pipeline").json()["columns"]["APPLIED"][0]
    assert card["application_id"] == apps[0]["id"]


def test_application_crud_validation_and_uniqueness(env: tuple[TestClient, Session]) -> None:
    client, session = env
    p, job = mk_profile(client, "a"), mk_job(session)
    created = client.post(f"{API}/profiles/{p}/applications", json={"job_id": job, "source": "referral", "notes": "n", "compensation_entered": "150k"})
    assert created.status_code == 201
    aid = created.json()["id"]
    assert client.post(f"{API}/profiles/{p}/applications", json={"job_id": job}).status_code == 409
    assert client.post(f"{API}/profiles/{p}/applications", json={"job_id": "nope"}).status_code == 404
    other_job = mk_job(session, "Other")
    updated = client.put(f"{API}/profiles/{p}/applications/{aid}", json={"job_id": other_job, "notes": "changed"})
    assert updated.json()["notes"] == "changed" and updated.json()["job_id"] == job  # the job cannot be re-pointed
    assert client.put(f"{API}/profiles/{p}/applications/{aid}", json={"job_id": job, "resume_variant_id": "nope"}).status_code == 404
    assert client.delete(f"{API}/profiles/{p}/applications/{aid}").status_code == 204
    assert client.get(f"{API}/profiles/{p}/applications/{aid}").status_code == 404


RECORDS: list[tuple[str, dict[str, Any]]] = [
    ("contacts", {"name": "Riley Recruiter", "company": "Contoso"}),
    ("follow-ups", {"due_at": NOW.isoformat()}),
    ("interviews", {"type": "coding", "scheduled_at": (NOW + timedelta(days=2)).isoformat()}),
]


@pytest.mark.parametrize(("path", "extra"), RECORDS, ids=[r[0] for r in RECORDS])
def test_tracking_records_are_invisible_to_other_profiles(env: tuple[TestClient, Session], path: str, extra: dict[str, Any]) -> None:
    client, session = env
    a, b = mk_profile(client, "a"), mk_profile(client, "b")
    job = mk_job(session)
    app_id = client.post(f"{API}/profiles/{a}/applications", json={"job_id": job}).json()["id"]
    body = {**extra, **({"application_id": app_id} if path != "contacts" else {})}
    rid = client.post(f"{API}/profiles/{a}/{path}", json=body).json()["id"]
    assert [r["id"] for r in client.get(f"{API}/profiles/{a}/{path}").json()] == [rid]
    assert client.get(f"{API}/profiles/{b}/{path}").json() == []
    if path != "follow-ups":
        assert client.get(f"{API}/profiles/{b}/{path}/{rid}").status_code in (404, 405)
    assert client.put(f"{API}/profiles/{b}/{path}/{rid}", json=body).status_code == 404
    assert client.delete(f"{API}/profiles/{b}/{path}/{rid}").status_code == 404
    # B cannot attach records to A's application either
    if path != "contacts":
        assert client.post(f"{API}/profiles/{b}/{path}", json=body).status_code == 404
    assert client.get(f"{API}/profiles/{a}/{path}").json()[0]["id"] == rid  # untouched


def test_applications_are_invisible_to_other_profiles(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = mk_profile(client, "a"), mk_profile(client, "b")
    job = mk_job(session)
    aid = client.post(f"{API}/profiles/{a}/applications", json={"job_id": job}).json()["id"]
    assert client.get(f"{API}/profiles/{b}/applications").json() == []
    base = f"{API}/profiles/{b}/applications/{aid}"
    assert client.get(base).status_code == 404 and client.put(base, json={"job_id": job}).status_code == 404
    assert client.delete(base).status_code == 404
    assert client.get(f"{base}/contacts").status_code == 404
    assert client.post(f"{base}/contacts", json={"contact_id": "x"}).status_code == 404
    # a contact of B cannot be linked to A's application, nor A's contact to B's application
    cb = client.post(f"{API}/profiles/{b}/contacts", json={"name": "B contact"}).json()["id"]
    assert client.post(f"{API}/profiles/{a}/applications/{aid}/contacts", json={"contact_id": cb}).status_code == 404


def test_contacts_link_roles_and_cleanup(env: tuple[TestClient, Session]) -> None:
    client, session = env
    p, job = mk_profile(client, "a"), mk_job(session)
    aid = client.post(f"{API}/profiles/{p}/applications", json={"job_id": job}).json()["id"]
    cid = client.post(f"{API}/profiles/{p}/contacts", json={"name": "Riley", "email": "riley@example.com"}).json()["id"]
    url = f"{API}/profiles/{p}/applications/{aid}/contacts"
    assert client.post(url, json={"contact_id": cid, "role": "recruiter"}).json()["role"] == "recruiter"
    assert client.post(url, json={"contact_id": cid, "role": "referral"}).json()["role"] == "referral"  # relink updates
    assert client.post(url, json={"contact_id": cid, "role": "wizard"}).status_code == 422
    assert [x["role"] for x in client.get(url).json()] == ["referral"]
    assert client.delete(f"{url}/{cid}").status_code == 204 and client.delete(f"{url}/{cid}").status_code == 404
    client.post(url, json={"contact_id": cid, "role": "interviewer"})
    assert client.delete(f"{API}/profiles/{p}/contacts/{cid}").status_code == 204  # links are removed with the contact
    assert client.get(url).json() == []


def test_follow_ups_due_list_and_lifecycle(env: tuple[TestClient, Session]) -> None:
    client, session = env
    p, job = mk_profile(client, "a"), mk_job(session)
    aid = client.post(f"{API}/profiles/{p}/applications", json={"job_id": job}).json()["id"]
    base = f"{API}/profiles/{p}/follow-ups"
    due = client.post(base, json={"application_id": aid, "due_at": (NOW - timedelta(hours=1)).isoformat(), "type": "check_in"}).json()
    client.post(base, json={"application_id": aid, "due_at": (NOW + timedelta(days=3)).isoformat()})
    overview = client.get(f"{API}/profiles/{p}/overview").json()
    assert [f["id"] for f in overview["due_follow_ups"]] == [due["id"]]  # only the overdue one
    assert client.post(f"{base}/{due['id']}/complete").json()["status"] == "DONE"
    assert client.get(f"{API}/profiles/{p}/overview").json()["due_follow_ups"] == []
    assert client.post(f"{base}/{due['id']}/reopen").json()["completed_at"] is None
    assert client.post(f"{base}/{due['id']}/dismiss").json()["status"] == "DISMISSED"
    assert client.post(f"{base}/{due['id']}/explode").status_code == 404
    assert len(client.get(base, params={"status": "OPEN"}).json()) == 1
    assert client.put(f"{base}/{due['id']}", json={"notes": "n"}).json()["notes"] == "n"


def test_interviews_upcoming_notes_and_validation(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = mk_profile(client, "a"), mk_profile(client, "b")
    job_a, job_b = mk_job(session, "A"), mk_job(session, "B")
    app_a = client.post(f"{API}/profiles/{a}/applications", json={"job_id": job_a}).json()["id"]
    app_b = client.post(f"{API}/profiles/{b}/applications", json={"job_id": job_b}).json()["id"]
    soon = client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_a, "type": "system_design", "scheduled_at": (NOW + timedelta(days=2)).isoformat(), "participants": ["Sam"]}).json()
    client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_a, "scheduled_at": (NOW - timedelta(days=2)).isoformat()})
    client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_a, "scheduled_at": (NOW + timedelta(days=60)).isoformat()})
    client.post(f"{API}/profiles/{b}/interviews", json={"application_id": app_b, "scheduled_at": (NOW + timedelta(days=1)).isoformat()})
    assert [i["id"] for i in client.get(f"{API}/profiles/{a}/overview").json()["upcoming_interviews"]] == [soon["id"]]
    assert len(client.get(f"{API}/profiles/{b}/overview").json()["upcoming_interviews"]) == 1  # only B's own
    assert len(client.get(f"{API}/profiles/{a}/interviews", params={"upcoming": "true"}).json()) == 2

    done = client.put(f"{API}/profiles/{a}/interviews/{soon['id']}", json={"application_id": app_a, "type": "system_design", "outcome": "PASSED", "post_notes": "went well", "next_steps": "send portfolio by Friday"})
    assert done.status_code == 200 and (done.json()["outcome"], done.json()["next_steps"]) == ("PASSED", "send portfolio by Friday")
    assert client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_a, "type": "karaoke"}).status_code == 422
    assert client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_a, "outcome": "MAYBE"}).status_code == 422
    assert client.post(f"{API}/profiles/{a}/interviews", json={"application_id": app_b}).status_code == 404  # B's application


def test_overview_metrics_come_from_the_profiles_own_history(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = mk_profile(client, "a"), mk_profile(client, "b")
    job1, job2 = mk_job(session, "One"), mk_job(session, "Two")
    to_applied(client, a, job1)
    move(client, a, job1, "SCREENING", "INTERVIEWING")
    to_applied(client, a, job2)
    move(client, b, job1, "REJECTED")
    m = client.get(f"{API}/profiles/{a}/overview").json()["metrics"]
    assert (m["jobs_reviewed"], m["shortlisted"], m["applications_submitted"], m["screens"], m["interviews"]) == (2, 2, 2, 1, 1)
    assert m["responded"] == 1 and m["response_rate"] == 0.5
    mb = client.get(f"{API}/profiles/{b}/overview").json()["metrics"]
    assert (mb["jobs_reviewed"], mb["applications_submitted"], mb["response_rate"]) == (1, 0, None)
    n = session.scalar(select(func.count()).select_from(JobStatusHistoryModel).where(JobStatusHistoryModel.profile_id == b))
    assert n == 1
