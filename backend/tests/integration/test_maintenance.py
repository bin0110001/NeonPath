from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from careerflow import worker
from careerflow.api.profiles import get_session as profiles_session
from careerflow.application.maintenance import PRUNED_MARKER, MaintenanceService
from careerflow.infrastructure.database.models import (
    Base,
    JobEvaluationModel,
    JobModel,
    JobSourceModel,
    JobSourceRecordModel,
    ProfileModel,
    SourceRunModel,
    TaskModel,
)
from careerflow.infrastructure.tasks.queue import SUCCEEDED
from careerflow.main import create_app
from careerflow.seed import seed_session

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
DESC = "A very specific description that must survive expiry."


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def service(session: Session) -> MaintenanceService:
    return MaintenanceService(session, clock=lambda: NOW)


def add_job(session: Session, title: str, adapter: str = "rss", seen_days_ago: float = 0, **extra: object) -> JobModel:
    job = JobModel(title=title, company="Contoso", description_text=DESC, **extra)
    session.add(job)
    session.flush()
    session.add(
        JobSourceRecordModel(
            job_id=job.id, adapter=adapter, external_id=title, raw_payload={"title": title},
            last_seen_at=NOW - timedelta(days=seen_days_ago),
        )
    )  # fmt: skip
    session.commit()
    return job


def working_source(session: Session, adapter: str = "rss", finished_days_ago: float = 0, status: str = "SUCCEEDED") -> None:
    source = JobSourceModel(name=f"{adapter}-{finished_days_ago}-{status}", adapter=adapter, config_json={})
    session.add(source)
    session.flush()
    session.add(SourceRunModel(source_id=source.id, status=status, finished_at=NOW - timedelta(days=finished_days_ago)))
    session.commit()


# --- expiration ---------------------------------------------------------------------------


def test_posting_past_its_expiry_is_marked_expired_and_keeps_its_description(session: Session) -> None:
    job = add_job(session, "Old", adapter="manual", expires_at=NOW - timedelta(days=1))
    fresh = add_job(session, "Fresh", adapter="manual", expires_at=NOW + timedelta(days=5))
    report = service(session).check_expiration()
    assert report.expired == 1
    session.refresh(job)
    session.refresh(fresh)
    assert job.source_status == "EXPIRED" and job.description_text == DESC
    assert fresh.source_status is None  # untouched
    assert len(job.source_records) == 1 and job.source_records[0].raw_payload == {"title": "Old"}


def test_listing_that_vanished_from_a_working_source_expires(session: Session) -> None:
    working_source(session, "rss")
    gone = add_job(session, "Gone", seen_days_ago=30)
    seen = add_job(session, "Seen", seen_days_ago=2)
    report = service(session).check_expiration(stale_days=14)
    assert report.expired == 1
    session.refresh(gone)
    session.refresh(seen)
    assert gone.source_status == "EXPIRED" and gone.description_text == DESC
    assert seen.source_status is None


def test_outage_does_not_expire_listings(session: Session) -> None:
    working_source(session, "rss", status="FAILED")  # the source itself is failing
    working_source(session, "rss", finished_days_ago=20)  # last success long ago
    job = add_job(session, "Maybe", seen_days_ago=30)
    assert service(session).check_expiration().expired == 0
    session.refresh(job)
    assert job.source_status is None


def test_job_with_one_fresh_record_is_not_expired_and_expired_jobs_revive(session: Session) -> None:
    working_source(session, "rss")
    job = add_job(session, "Two sources", seen_days_ago=40)
    session.add(JobSourceRecordModel(job_id=job.id, adapter="rss", external_id="b", raw_payload={"x": 1}, last_seen_at=NOW))
    session.commit()
    assert service(session).check_expiration().expired == 0
    stale = add_job(session, "Stale", seen_days_ago=40)
    service(session).check_expiration()
    session.refresh(stale)
    assert stale.source_status == "EXPIRED"
    stale.source_records[0].last_seen_at = NOW  # the source lists it again
    session.commit()
    report = service(session).check_expiration()
    session.refresh(stale)
    assert report.revived == 1 and stale.source_status == "ACTIVE"


def test_merged_duplicates_are_ignored(session: Session) -> None:
    working_source(session, "rss")
    keep = add_job(session, "Keep", seen_days_ago=40)
    dup = add_job(session, "Dup", seen_days_ago=40)
    dup.merged_into_id = keep.id
    session.commit()
    service(session).check_expiration()
    session.refresh(dup)
    assert dup.source_status is None


# --- retention ----------------------------------------------------------------------------------


def test_prune_replaces_old_payloads_only_and_keeps_job_text(session: Session) -> None:
    old = add_job(session, "Old", seen_days_ago=120)
    new = add_job(session, "New", seen_days_ago=10)
    assert service(session).prune_raw_payloads(90) == 1
    session.refresh(old)
    session.refresh(new)
    payload = old.source_records[0].raw_payload
    assert payload[PRUNED_MARKER] is True and "title" not in payload
    assert new.source_records[0].raw_payload == {"title": "New"}
    assert old.description_text == DESC and old.title == "Old"
    assert service(session).prune_raw_payloads(90) == 0  # idempotent


def test_prune_with_zero_days_keeps_everything(session: Session) -> None:
    add_job(session, "Ancient", seen_days_ago=5000)
    assert service(session).prune_raw_payloads(0) == 0


# --- re-evaluation ----------------------------------------------------------------------------------


def seeded(session: Session) -> dict[str, str]:
    seed_session(session)
    return {p.slug: p.id for p in session.scalars(select(ProfileModel))}


def evaluations(session: Session, profile_id: str) -> int:
    return int(session.scalar(select(func.count()).select_from(JobEvaluationModel).where(JobEvaluationModel.profile_id == profile_id)) or 0)


def test_reevaluation_appends_rows_for_that_profile_only(session: Session) -> None:
    ids = seeded(session)
    jordan, morgan = ids["jordan-lee"], ids["morgan-rivera"]
    before = (evaluations(session, jordan), evaluations(session, morgan))
    assert service(session).reevaluate_profile(jordan) == 4
    assert (evaluations(session, jordan), evaluations(session, morgan)) == (before[0] + 4, before[1])


def test_reevaluation_requests_coalesce(session: Session) -> None:
    jordan = seeded(session)["jordan-lee"]
    first = service(session).request_reevaluation(jordan)
    assert first is not None and first.task_type == "reevaluate_profile"
    assert service(session).request_reevaluation(jordan) is None  # already waiting
    assert session.scalar(select(func.count()).select_from(TaskModel)) == 1


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Generator[TestClient]:
    app = create_app()

    def override() -> Generator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[profiles_session] = override
    yield TestClient(app)


def test_editing_profile_data_triggers_reevaluation_of_that_profile_only(client: TestClient, factory: sessionmaker[Session]) -> None:
    with factory() as session:
        ids = seeded(session)
    jordan, morgan = ids["jordan-lee"], ids["morgan-rivera"]
    with factory() as session:
        before = {k: evaluations(session, v) for k, v in ids.items()}

    base = f"/api/v1/profiles/{jordan}"
    assert client.put(f"{base}/search-preferences", json={"remote_preference": "PREFERRED"}).status_code == 200
    assert client.put(f"{base}/scoring-preferences", json={"weights": {"role_alignment": 1.0}}).status_code == 200  # coalesced
    with factory() as session:
        tasks = list(session.scalars(select(TaskModel)))
    assert [(t.task_type, t.profile_id) for t in tasks] == [("reevaluate_profile", jordan)]  # not morgan, once

    assert worker.run_one(factory, "w1") is True
    with factory() as session:
        done = session.scalars(select(TaskModel)).one()
        assert done.status == SUCCEEDED and done.metadata_json == {"jobs": 4}
        assert evaluations(session, jordan) == before["jordan-lee"] + 4
        assert evaluations(session, morgan) == before["morgan-rivera"]  # untouched

    # new evaluation reflects the edited preferences
    with factory() as session:
        latest = session.scalars(
            select(JobEvaluationModel).where(JobEvaluationModel.profile_id == jordan).order_by(JobEvaluationModel.created_at.desc())
        ).first()
        assert latest is not None and set(latest.dimension_scores_json) >= {"role_alignment"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "role-families", {"name": "New family"}),
        ("post", "role-targets", {"title_pattern": "staff*"}),
        ("post", "skills", {"canonical_name": "Rust"}),
    ],
)
def test_other_profile_data_edits_also_trigger_reevaluation(
    client: TestClient, factory: sessionmaker[Session], method: str, path: str, body: dict[str, object]
) -> None:
    with factory() as session:
        jordan = seeded(session)["jordan-lee"]
    assert getattr(client, method)(f"/api/v1/profiles/{jordan}/{path}", json=body).status_code == 201
    with factory() as session:
        assert [t.task_type for t in session.scalars(select(TaskModel))] == ["reevaluate_profile"]


def test_non_evaluation_data_does_not_trigger_reevaluation(client: TestClient, factory: sessionmaker[Session]) -> None:
    with factory() as session:
        jordan = seeded(session)["jordan-lee"]
    assert client.post(f"/api/v1/profiles/{jordan}/portfolio", json={"name": "Repo"}).status_code == 201
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TaskModel)) == 0


# --- worker handlers --------------------------------------------------------------------------------


def test_worker_runs_maintenance_handlers(factory: sessionmaker[Session]) -> None:
    from careerflow.infrastructure.tasks.queue import TaskQueue

    with factory() as session:
        queue = TaskQueue(session)
        queue.enqueue("check_expiration")
        queue.enqueue("prune_raw_payloads")
    assert worker.run_one(factory, "w1") and worker.run_one(factory, "w1")
    with factory() as session:
        done = {t.task_type: t for t in session.scalars(select(TaskModel))}
        assert done["check_expiration"].status == SUCCEEDED and done["check_expiration"].metadata_json == {"expired": 0, "revived": 0}
        assert done["prune_raw_payloads"].status == SUCCEEDED and "pruned" in done["prune_raw_payloads"].metadata_json
