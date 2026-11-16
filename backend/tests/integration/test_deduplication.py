from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.duplicates import get_session as duplicates_session
from careerflow.api.jobs import get_session as jobs_session
from careerflow.api.profiles import get_session as profiles_session
from careerflow.application.jobs.dedup import DedupError, DedupService
from careerflow.application.jobs.workflow import JobWorkflowService
from careerflow.application.sources.ingest import IngestionService
from careerflow.domain.jobs.dedup import DISTINCT, EXACT, LIKELY, POSSIBLE, JobSignature, match
from careerflow.domain.jobs.workflow import WorkflowStatus
from careerflow.infrastructure.database.models import (
    Base,
    JobModel,
    JobSourceRecordModel,
    ProfileModel,
)
from careerflow.infrastructure.jobsources.simple import FixtureJobAdapter
from careerflow.main import create_app

DESC = "Build and operate internal developer platforms with Python, Kubernetes and Terraform for product teams."
BASE = {
    "title": "Platform Engineer",
    "company": "Contoso Labs",
    "description_text": DESC,
    "location_text": "Austin, TX",
}


def sig(**kw: object) -> JobSignature:
    values: dict[str, object] = {"company": "Contoso Labs", "title": "Platform Engineer", "location": "Austin, TX", "description": DESC}
    values.update(kw)
    return JobSignature(**values)  # type: ignore[arg-type]


# --- domain matching ----------------------------------------------------------------------


def test_exact_same_posting_despite_noise() -> None:
    result = match(sig(company="Contoso Labs, Inc."), sig(title="platform  engineer!", location="Austin TX (Hybrid)"))
    assert result.classification == EXACT and result.score == 1.0


def test_requisition_id_is_exact() -> None:
    a, b = sig(requisition_id="R-7", title="Platform Eng"), sig(requisition_id="R-7", title="Senior Platform Engineer II")
    assert match(a, b).classification == EXACT


def test_likely_when_wording_differs_slightly() -> None:
    other = sig(title="Platform Engineer (Remote)", location="Remote - US", description=DESC + " Join us today.")
    result = match(sig(), other)
    assert result.classification in (LIKELY, POSSIBLE) and 0.6 <= result.score < 1.0
    assert result.reasons[0] == "same company"


def test_different_company_or_title_is_distinct() -> None:
    assert match(sig(), sig(company="Fabrikam")).classification == DISTINCT
    unrelated = sig(title="Chief Marketing Officer", description="Lead brand strategy and campaigns worldwide.", location="Berlin")
    assert match(sig(), unrelated).classification == DISTINCT


def test_boilerplate_cannot_rescue_a_different_title() -> None:
    other = sig(title="Account Executive", location="Chicago")
    assert match(sig(), other).classification == DISTINCT


def test_posted_date_and_salary_contribute() -> None:
    near = match(
        sig(title="Platform Engineer II", posted_at=datetime(2026, 10, 1, tzinfo=UTC), salary_min=100, salary_max=120),
        sig(posted_at=datetime(2026, 10, 3, tzinfo=UTC), salary_min=105, salary_max=125),
    )
    far = match(
        sig(title="Platform Engineer II", posted_at=datetime(2026, 1, 1, tzinfo=UTC), salary_min=10, salary_max=20),
        sig(posted_at=datetime(2026, 10, 3, tzinfo=UTC), salary_min=105, salary_max=125),
    )
    assert near.score > far.score


# --- ingestion + review ---------------------------------------------------------------------


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def ingest(session: Session, items: list[dict[str, object]], name: str = "fixture"):  # type: ignore[no-untyped-def]
    adapter = FixtureJobAdapter({"items": items})
    adapter.name = name
    return IngestionService(session, sleep=lambda _s: None).ingest(adapter)


def test_same_job_from_two_sources_is_one_canonical_job_with_two_records(session: Session) -> None:
    first = ingest(session, [{**BASE, "external_id": "a-1"}], name="rss")
    second = ingest(session, [{**BASE, "external_id": "gh-9", "location_text": "Austin, TX (Hybrid)"}], name="greenhouse")
    assert len(first.created) == 1 and len(second.created) == 0 and len(second.attached_jobs) == 1
    jobs = list(session.scalars(select(JobModel)))
    assert len(jobs) == 1
    records = list(session.scalars(select(JobSourceRecordModel)))
    assert {(r.adapter, r.external_id) for r in records} == {("rss", "a-1"), ("greenhouse", "gh-9")}
    assert {r.job_id for r in records} == {jobs[0].id}
    again = ingest(session, [{**BASE, "external_id": "gh-9"}], name="greenhouse")  # refresh, not duplicate
    assert again.updated == 1 and len(list(session.scalars(select(JobSourceRecordModel)))) == 2


def test_probable_duplicates_are_queued_for_review_not_merged(session: Session) -> None:
    ingest(session, [{**BASE, "external_id": "1"}])
    ingest(session, [{**BASE, "external_id": "2", "title": "Platform Engineer (Remote)", "location_text": "Remote - US"}])
    assert len(list(session.scalars(select(JobModel)))) == 2
    pending = DedupService(session).list_duplicates()
    assert len(pending) == 1 and pending[0].classification in (LIKELY, POSSIBLE)
    assert "same company" in pending[0].reasons
    ingest(session, [{**BASE, "external_id": "2", "title": "Platform Engineer (Remote)", "location_text": "Remote - US"}])
    assert len(DedupService(session).list_duplicates()) == 1  # scanning is idempotent per pair


def test_unrelated_jobs_never_enter_the_review_queue(session: Session) -> None:
    ingest(session, [{**BASE, "external_id": "1"}, {**BASE, "external_id": "2", "company": "Fabrikam"}])
    ingest(session, [{**BASE, "external_id": "3", "title": "Sales Director", "description_text": "Close enterprise deals.", "location_text": "Paris"}])
    assert DedupService(session).list_duplicates() == []


def make_pair(session: Session) -> tuple[JobModel, JobModel]:
    ingest(session, [{**BASE, "external_id": "1"}], name="rss")
    ingest(session, [{**BASE, "external_id": "2", "title": "Platform Engineer (Remote)", "location_text": "Remote - US"}], name="greenhouse")
    older, newer = sorted(session.scalars(select(JobModel)), key=lambda j: (j.discovered_at, j.id))
    return older, newer


def test_merge_moves_records_hides_duplicate_and_unmerge_restores_everything(session: Session) -> None:
    older, newer = make_pair(session)
    profile = ProfileModel(slug="p", display_name="P")
    session.add(profile)
    session.commit()
    workflow = JobWorkflowService(session)
    workflow.transition(profile.id, newer.id, WorkflowStatus.SHORTLISTED, "user", "liked it")
    older_id, newer_id = older.id, newer.id
    before = {r.id: r.job_id for r in session.scalars(select(JobSourceRecordModel))}

    service = DedupService(session)
    (pair,) = service.list_duplicates()
    merge = service.merge_duplicate(pair.id, actor="tester")
    assert merge.canonical_job_id == older_id and merge.merged_job_id == newer_id

    session.expire_all()
    assert {r.job_id for r in session.scalars(select(JobSourceRecordModel))} == {older_id}
    assert session.get(JobModel, newer_id).merged_into_id == older_id  # type: ignore[union-attr]
    assert service.list_duplicates("PENDING") == [] and len(service.list_duplicates("MERGED")) == 1
    # workflow state/history of the merged job are untouched, not lost
    assert workflow.get_status(profile.id, newer_id) == WorkflowStatus.SHORTLISTED
    assert len(workflow.history(profile.id, newer_id)) == 1

    service.unmerge(merge.id)
    session.expire_all()
    assert {r.id: r.job_id for r in session.scalars(select(JobSourceRecordModel))} == before
    assert session.get(JobModel, newer_id).merged_into_id is None  # type: ignore[union-attr]
    assert workflow.get_status(profile.id, newer_id) == WorkflowStatus.SHORTLISTED
    assert len(service.list_duplicates("PENDING")) == 1  # back in the review queue
    with pytest.raises(DedupError, match="already undone"):
        service.unmerge(merge.id)


def test_merge_can_keep_the_newer_job_and_guards_invalid_merges(session: Session) -> None:
    older, newer = make_pair(session)
    service = DedupService(session)
    (pair,) = service.list_duplicates()
    with pytest.raises(DedupError, match="keep_job_id"):
        service.merge_duplicate(pair.id, keep_job_id="nope")
    merge = service.merge_duplicate(pair.id, keep_job_id=newer.id)
    assert merge.canonical_job_id == newer.id and merge.merged_job_id == older.id
    with pytest.raises(DedupError, match="already MERGED"):
        service.merge_duplicate(pair.id)
    with pytest.raises(DedupError, match="itself"):
        service.merge_jobs(newer.id, newer.id)
    with pytest.raises(DedupError, match="already merged"):
        service.merge_jobs(newer.id, older.id)


def test_dismiss_removes_the_pair_from_review(session: Session) -> None:
    make_pair(session)
    service = DedupService(session)
    (pair,) = service.list_duplicates()
    assert service.dismiss(pair.id).status == "DISMISSED"
    assert service.list_duplicates() == []
    with pytest.raises(DedupError):
        service.dismiss(pair.id)


# --- API ----------------------------------------------------------------------------------------


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    for dependency in (duplicates_session, jobs_session, profiles_session):
        app.dependency_overrides[dependency] = lambda: session
    yield TestClient(app)


def test_api_review_merge_unmerge_and_inbox_visibility(client: TestClient, session: Session) -> None:
    profile = ProfileModel(slug="p", display_name="P")
    session.add(profile)
    session.commit()
    older, newer = make_pair(session)

    def inbox() -> list[str]:
        return [j["id"] for j in client.get("/api/v1/jobs", params={"profile_id": profile.id}).json()]

    assert set(inbox()) == {older.id, newer.id}
    (pair,) = client.get("/api/v1/duplicates").json()
    assert pair["canonical"]["id"] == older.id and pair["job"]["id"] == newer.id
    assert pair["score"] >= 0.6 and pair["reasons"]
    assert pair["canonical"]["source_count"] == 1

    merged = client.post(f"/api/v1/duplicates/{pair['id']}/merge", json={"actor": "me"})
    assert merged.status_code == 200
    assert inbox() == [older.id]  # the duplicate is hidden
    assert client.get(f"/api/v1/jobs/{newer.id}").json()["merged_into_id"] == older.id
    assert client.get(f"/api/v1/jobs/{older.id}/sources").json().__len__() == 2
    assert client.post(f"/api/v1/duplicates/{pair['id']}/merge").status_code == 409
    assert len(client.get("/api/v1/merges").json()) == 1

    assert client.post(f"/api/v1/merges/{merged.json()['id']}/unmerge").status_code == 200
    assert set(inbox()) == {older.id, newer.id}
    assert client.post(f"/api/v1/merges/{merged.json()['id']}/unmerge").status_code == 409
    assert client.post("/api/v1/merges/nope/unmerge").status_code == 404
    assert client.post("/api/v1/duplicates/nope/dismiss").status_code == 404


def test_api_manual_merge_of_two_known_duplicates(client: TestClient, session: Session) -> None:
    a = JobModel(title="A", company="X", description_text="d")
    b = JobModel(title="B", company="Y", description_text="d")
    session.add_all([a, b])
    session.commit()
    created = client.post("/api/v1/merges", json={"canonical_job_id": a.id, "merged_job_id": b.id})
    assert created.status_code == 201
    assert client.post("/api/v1/merges", json={"canonical_job_id": a.id, "merged_job_id": a.id}).status_code == 409
