from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.sources import get_session
from careerflow.application.sources.ingest import IngestionService, RateLimiter, RetryPolicy
from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    NormalizedJob,
    SourceCapabilities,
    SourceFetchError,
    SourceJobDocument,
    SourceJobReference,
    SourceRateLimitedError,
)
from careerflow.infrastructure.database.models import (
    Base,
    JobModel,
    JobRequirementModel,
    JobSourceModel,
    JobSourceRecordModel,
    SourceRunModel,
)
from careerflow.infrastructure.jobsources import registry
from careerflow.infrastructure.jobsources.registry import mask_config, resolve_env_secrets
from careerflow.infrastructure.jobsources.simple import FixtureJobAdapter
from careerflow.main import create_app

ITEM = {
    "title": "Platform Engineer",
    "company": "Contoso Labs",
    "description_text": "Build platforms.",
    "location_text": "Austin, TX",
    "external_id": "c-1",
    "requirements": [{"type": "skill", "normalized_text": "Python", "source_text": "Python"}],
}


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def service(session: Session, **kw: Any) -> IngestionService:
    return IngestionService(session, sleep=lambda _s: None, **kw)


def count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_ingest_persists_canonical_job_source_record_and_requirements(session: Session) -> None:
    result = service(session).ingest(FixtureJobAdapter({"items": [ITEM]}))
    assert (result.discovered, len(result.created), result.updated, result.failed) == (1, 1, 0, 0)
    job = session.scalars(select(JobModel)).one()
    assert job.status == "READY_FOR_REVIEW" and job.fingerprint
    record = session.scalars(select(JobSourceRecordModel)).one()
    assert (record.adapter, record.external_id, record.job_id) == ("fixture", "c-1", job.id)
    assert record.raw_payload["company"] == "Contoso Labs"  # raw snapshot retained
    assert count(session, JobRequirementModel) == 1


def test_reingesting_refreshes_instead_of_duplicating(session: Session) -> None:
    svc = service(session)
    svc.ingest(FixtureJobAdapter({"items": [ITEM]}))
    again = svc.ingest(FixtureJobAdapter({"items": [{**ITEM, "description_text": "Changed text"}]}))
    assert len(again.created) == 0 and again.updated == 1
    assert count(session, JobModel) == 1 and count(session, JobSourceRecordModel) == 1
    assert session.scalars(select(JobSourceRecordModel)).one().raw_payload["description_text"] == "Changed text"


def test_one_bad_item_does_not_stop_the_batch(session: Session) -> None:
    result = service(session).ingest(FixtureJobAdapter({"items": [{"title": "broken", "external_id": "x"}, ITEM]}))
    assert (len(result.created), result.failed) == (1, 1)
    assert "missing required field" in result.errors[0]


class FlakyAdapter:
    name = "flaky"
    capabilities = SourceCapabilities(access_method="test", rate_limit_per_minute=60)

    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls = 0

    def discover(self, request: DiscoveryRequest):  # type: ignore[no-untyped-def]
        yield SourceJobReference("f-1")

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return SourceJobDocument(reference, dict(ITEM))

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        return FixtureJobAdapter({"items": [ITEM]}).normalize(document)


def test_transient_errors_are_retried_with_backoff_then_succeed(session: Session) -> None:
    sleeps: list[float] = []
    clock = iter(range(1000, 2000))
    svc = IngestionService(
        session, retry=RetryPolicy(3, 2.0), sleep=sleeps.append, clock=lambda: float(next(clock))
    )
    adapter = FlakyAdapter([SourceFetchError("500"), SourceRateLimitedError("429", retry_after_seconds=30)])
    result = svc.ingest(adapter)
    assert len(result.created) == 1 and adapter.calls == 3
    assert 2.0 in sleeps and 30.0 in sleeps  # exponential backoff, and Retry-After wins when larger


def test_non_retryable_and_exhausted_errors_fail_the_item(session: Session) -> None:
    permanent = FlakyAdapter([SourceFetchError("404", retryable=False)])
    result = service(session).ingest(permanent)
    assert permanent.calls == 1 and result.failed == 1
    tired = FlakyAdapter([SourceFetchError("500")] * 5)
    result = service(session, retry=RetryPolicy(3, 0.0)).ingest(tired)
    assert tired.calls == 3 and result.failed == 1


def test_rate_limiter_spaces_calls_by_declared_limit() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(30, lambda: now[0], sleep)  # 30/min -> 2s apart
    limiter.wait()
    now[0] += 0.5
    limiter.wait()
    limiter.wait()
    assert sleeps == [pytest.approx(1.5), pytest.approx(2.0)]
    assert RateLimiter(None, lambda: now[0], sleep).interval == 0


def test_run_history_and_health_transitions(session: Session) -> None:
    source = JobSourceModel(name="demo", adapter="fixture", config_json={"items": [ITEM]})
    broken = JobSourceModel(name="broken", adapter="fixture", config_json={})
    mixed = JobSourceModel(name="mixed", adapter="fixture", config_json={"items": [{"title": "x"}, {**ITEM, "external_id": "c-9"}]})
    session.add_all([source, broken, mixed])
    session.commit()
    svc = service(session)

    run = svc.run_source(source.id)
    assert (run.status, run.created, run.discovered) == ("SUCCEEDED", 1, 1)
    assert source.health == "HEALTHY" and source.last_status == "SUCCEEDED" and source.last_run_at

    for expected_failures, expected_health in ((1, "DEGRADED"), (2, "DEGRADED"), (3, "FAILING")):
        failed = svc.run_source(broken.id)
        assert failed.status == "FAILED" and failed.error_code == "SourceConfigError"
        assert (broken.consecutive_failures, broken.health) == (expected_failures, expected_health)
    assert "needs 'items' or 'path'" in (broken.last_error or "")

    partial = svc.run_source(mixed.id)
    assert (partial.status, partial.created, partial.failed) == ("PARTIAL", 1, 1)
    assert mixed.health == "DEGRADED"

    assert count(session, SourceRunModel) == 5
    svc.run_source(source.id)  # recovery resets the counter
    assert source.consecutive_failures == 0 and source.health == "HEALTHY"


def test_adapter_crash_is_recorded_not_raised(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    class Crashy(FlakyAdapter):
        def discover(self, request: DiscoveryRequest):  # type: ignore[no-untyped-def]
            raise RuntimeError("bug with token=abcdef123456")

    monkeypatch.setitem(registry.ADAPTERS, "crashy", lambda config, http: Crashy([]))
    source = JobSourceModel(name="c", adapter="crashy", config_json={})
    session.add(source)
    session.commit()
    run = service(session).run_source(source.id)
    assert run.status == "FAILED" and run.error_code == "RuntimeError"
    assert "abcdef123456" not in (run.error_message or "")


def test_new_adapter_needs_only_registration(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-006 acceptance: adding a source touches the registry only."""
    monkeypatch.setitem(registry.ADAPTERS, "custom", lambda config, http: FlakyAdapter([]))
    source = JobSourceModel(name="custom-src", adapter="custom", config_json={})
    session.add(source)
    session.commit()
    assert service(session).run_source(source.id).status == "SUCCEEDED"


def test_secrets_resolve_from_environment_and_are_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_SOURCE_KEY", "value-123456")
    assert resolve_env_secrets({"api_key_env": "MY_SOURCE_KEY"})["api_key"] == "value-123456"
    with pytest.raises(Exception, match="NOPE"):
        resolve_env_secrets({"token_env": "NOPE"})
    assert mask_config({"api_key": "x", "api_key_env": "MY_SOURCE_KEY", "board": "acme"}) == {
        "api_key": "***", "api_key_env": "MY_SOURCE_KEY", "board": "acme",
    }  # fmt: skip


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()

    def override() -> Generator[Session]:
        yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)


def test_sources_api_lifecycle(client: TestClient) -> None:
    assert {"manual", "fixture"} <= set(client.get("/api/v1/sources/adapters").json())
    assert client.post("/api/v1/sources", json={"name": "x", "adapter": "nope"}).status_code == 422
    assert client.post("/api/v1/sources", json={"name": "x", "adapter": "fixture", "config": {}}).status_code == 422
    inline = client.post(
        "/api/v1/sources", json={"name": "x", "adapter": "fixture", "config": {"items": [], "api_key": "sk-1"}}
    )
    assert inline.status_code == 422 and "api_key_env" in inline.text

    created = client.post("/api/v1/sources", json={"name": "Demo", "adapter": "fixture", "config": {"items": [ITEM]}})
    assert created.status_code == 201
    sid = created.json()["id"]
    assert client.post("/api/v1/sources", json={"name": "Demo", "adapter": "fixture", "config": {"items": []}}).status_code == 409

    run = client.post(f"/api/v1/sources/{sid}/run")
    assert run.status_code == 200 and run.json()["status"] == "SUCCEEDED" and run.json()["created"] == 1
    runs = client.get(f"/api/v1/sources/{sid}/runs").json()
    assert [r["status"] for r in runs] == ["SUCCEEDED"]
    listed = client.get("/api/v1/sources").json()[0]
    assert listed["health"] == "HEALTHY" and listed["last_status"] == "SUCCEEDED"

    assert client.patch(f"/api/v1/sources/{sid}", json={"enabled": False}).json()["enabled"] is False
    assert client.post(f"/api/v1/sources/{sid}/run").status_code == 409
    assert client.delete(f"/api/v1/sources/{sid}").status_code == 204
    assert client.get("/api/v1/sources").json() == []
    assert client.post("/api/v1/sources/nope/run").status_code == 404


def test_manual_import_goes_through_the_framework(client: TestClient, session: Session) -> None:
    from careerflow.api.jobs import get_session as jobs_session

    client.app.dependency_overrides[jobs_session] = lambda: session  # type: ignore[attr-defined]
    body = {"title": "Pasted", "company": "Acme", "description_text": "Text", "source": {"adapter": "manual", "source_url": "https://e.com/1"}}
    first = client.post("/api/v1/jobs/import", json=body)
    second = client.post("/api/v1/jobs/import", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]  # two pastes are two postings
    record = session.scalars(select(JobSourceRecordModel)).first()
    assert record is not None and record.adapter == "manual" and record.source_url == "https://e.com/1"
    bad = client.post("/api/v1/jobs/import", json={**body, "description_text": ""})
    assert bad.status_code == 422
