from __future__ import annotations

import os
import threading
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from careerflow import worker
from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.searches import get_session as searches_session
from careerflow.application.scheduling import SchedulerService
from careerflow.application.searches import make_filter
from careerflow.domain.sources.ports import NormalizedJob
from careerflow.infrastructure.database.models import (
    Base,
    JobEvaluationModel,
    JobModel,
    JobSourceModel,
    ProfileModel,
    ScheduledTaskModel,
    SearchRunModel,
    TaskModel,
)
from careerflow.infrastructure.tasks.queue import FAILED, QUEUED, SUCCEEDED
from careerflow.main import create_app

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ITEMS = [
    {"title": "Platform Engineer", "company": "Contoso", "description_text": "Python and Kubernetes", "external_id": "1", "remote_type": "REMOTE"},
    {"title": "Data Scientist", "company": "Contoso", "description_text": "SQL and forecasting", "external_id": "2", "remote_type": "ONSITE"},
    {"title": "Sales Manager", "company": "Contoso", "description_text": "Close deals", "external_id": "3", "remote_type": "ONSITE"},
]


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def world(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory() as session:
        a, b = ProfileModel(slug="a", display_name="A"), ProfileModel(slug="b", display_name="B")
        source = JobSourceModel(name="demo", adapter="fixture", config_json={"items": ITEMS})
        session.add_all([a, b, source])
        session.commit()
        return {"a": a.id, "b": b.id, "source": source.id}


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Generator[TestClient]:
    app = create_app()

    def override() -> Generator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[searches_session] = override
    app.dependency_overrides[profiles_session] = override
    yield TestClient(app)


def create(client: TestClient, profile: str, source: str, **extra: object) -> dict[str, object]:
    body = {"name": "Platform roles", "source_id": source, **extra}
    response = client.post(f"/api/v1/profiles/{profile}/searches", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- scheduler -----------------------------------------------------------------------------


def test_due_schedules_are_enqueued_once_and_rescheduled(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        scheduler = SchedulerService(session, clock)
        scheduler.upsert("k", "noop", 600, {"x": 1})
        assert scheduler.tick() == []  # not due yet
        clock.advance(601)
        (task,) = scheduler.tick()
        assert task.task_type == "noop" and task.status == QUEUED
        assert task.payload_json == {"x": 1, "trigger": "schedule", "schedule_key": "k"}
        assert scheduler.tick() == []  # the same occurrence is never enqueued twice
        row = session.scalars(select(ScheduledTaskModel)).one()
        assert row.last_task_id == task.id
        assert row.next_run_at.replace(tzinfo=UTC) == clock.now + timedelta(seconds=600)


def test_overlapping_occurrences_are_skipped_not_piled_up(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        scheduler = SchedulerService(session, clock)
        scheduler.upsert("k", "noop", 60)
        clock.advance(61)
        assert len(scheduler.tick()) == 1  # still QUEUED (no worker ran it)
        clock.advance(61)
        assert scheduler.tick() == []
        assert session.scalar(select(func.count()).select_from(TaskModel)) == 1


def test_upsert_changes_interval_and_disable_stops_enqueueing(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        scheduler = SchedulerService(session, clock)
        scheduler.upsert("k", "noop", 60)
        scheduler.upsert("k", "noop", 3600)
        clock.advance(120)
        assert scheduler.tick() == []  # the interval change pushed the next run out
        scheduler.upsert("k", "noop", 60, enabled=False)
        clock.advance(7200)
        assert scheduler.tick() == []
        scheduler.remove("k")
        assert session.scalar(select(func.count()).select_from(ScheduledTaskModel)) == 0


def test_maintenance_schedules_are_registered_once(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        scheduler = SchedulerService(session, Clock())
        scheduler.ensure_maintenance_schedules()
        scheduler.ensure_maintenance_schedules()
        keys = set(session.scalars(select(ScheduledTaskModel.key)))
        assert keys == {"maintenance:expiration", "maintenance:prune"}


POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_DATABASE_URL to a PostgreSQL database")
def test_concurrent_schedulers_enqueue_each_occurrence_exactly_once() -> None:
    assert POSTGRES_URL
    engine = create_engine(POSTGRES_URL, pool_size=10)
    Base.metadata.create_all(engine)  # full schema: task tables have foreign keys to profiles
    with sessionmaker(engine)() as cleanup:  # empty the queue tables; the schema itself is shared
        cleanup.execute(delete(TaskModel))
        cleanup.commit()
    factory = sessionmaker(engine, expire_on_commit=False)
    clock = Clock()
    with factory() as session:
        for i in range(20):
            SchedulerService(session, clock).upsert(f"k{i}", "noop", 60)
    clock.advance(61)

    def run() -> None:
        with factory() as session:
            SchedulerService(session, clock).tick()

    threads = [threading.Thread(target=run) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with factory() as session:
        keys = [t.payload_json["schedule_key"] for t in session.scalars(select(TaskModel))]
    assert sorted(keys) == sorted(f"k{i}" for i in range(20))  # exactly one task per schedule
    with sessionmaker(engine)() as cleanup:
        cleanup.execute(delete(ScheduledTaskModel))
        cleanup.execute(delete(TaskModel))
        cleanup.commit()


# --- searches --------------------------------------------------------------------------------


def test_run_now_records_a_run_and_evaluates_for_the_owning_profile_only(
    client: TestClient, factory: sessionmaker[Session], world: dict[str, str]
) -> None:
    search = create(client, world["a"], world["source"])
    run = client.post(f"/api/v1/profiles/{world['a']}/searches/{search['id']}/run")
    assert run.status_code == 200
    body = run.json()
    assert (body["status"], body["discovered"], body["created"], body["failed"]) == ("SUCCEEDED", 3, 3, 0)
    assert body["trigger"] == "manual" and body["source_run_id"]
    history = client.get(f"/api/v1/profiles/{world['a']}/searches/{search['id']}/runs").json()
    assert [r["id"] for r in history] == [body["id"]]
    with factory() as session:
        evaluated_for = set(session.scalars(select(JobEvaluationModel.profile_id)))
        assert evaluated_for == {world["a"]}  # profile B was not evaluated
        assert session.scalar(select(func.count()).select_from(JobModel)) == 3
    listed = client.get(f"/api/v1/profiles/{world['a']}/searches").json()[0]
    assert listed["last_run_at"] is not None


def test_filters_decide_what_is_stored(client: TestClient, factory: sessionmaker[Session], world: dict[str, str]) -> None:
    search = create(
        client, world["a"], world["source"],
        filters={"keywords_any": ["python", "sql"], "exclude_keywords": ["forecasting"], "remote_type": "REMOTE"},
    )  # fmt: skip
    body = client.post(f"/api/v1/profiles/{world['a']}/searches/{search['id']}/run").json()
    assert (body["created"], body["skipped"]) == (1, 2)
    with factory() as session:
        assert [j.title for j in session.scalars(select(JobModel))] == ["Platform Engineer"]


def test_make_filter_unit() -> None:
    job = NormalizedJob("Data Engineer", "X", "Spark and Python", "1", remote_type="HYBRID")
    assert make_filter({}) is None
    assert make_filter({"keywords_any": ["python"]})(job)  # type: ignore[misc]
    assert not make_filter({"keywords_any": ["rust"]})(job)  # type: ignore[misc]
    assert not make_filter({"exclude_keywords": ["spark"]})(job)  # type: ignore[misc]
    assert not make_filter({"remote_type": "remote"})(job)  # type: ignore[misc]


def test_source_errors_are_visible_in_the_run_history(client: TestClient, factory: sessionmaker[Session], world: dict[str, str]) -> None:
    with factory() as session:
        broken = JobSourceModel(name="broken", adapter="fixture", config_json={})
        session.add(broken)
        session.commit()
        broken_id = broken.id
    search = create(client, world["a"], broken_id)
    run = client.post(f"/api/v1/profiles/{world['a']}/searches/{search['id']}/run").json()
    assert run["status"] == "FAILED" and run["error_code"] == "SourceConfigError"
    assert "items" in run["error_message"]
    with factory() as session:
        assert session.get(JobSourceModel, broken_id).health == "DEGRADED"  # type: ignore[union-attr]


def test_schedule_is_created_updated_and_removed_with_the_search(client: TestClient, factory: sessionmaker[Session], world: dict[str, str]) -> None:
    search = create(client, world["a"], world["source"], schedule_minutes=30)
    assert search["next_run_at"] is not None
    url = f"/api/v1/profiles/{world['a']}/searches/{search['id']}"
    with factory() as session:
        row = session.scalars(select(ScheduledTaskModel)).one()
        assert (row.task_type, row.interval_seconds, row.profile_id) == ("run_search", 1800, world["a"])
        assert row.payload_json == {"search_id": search["id"]}
    assert client.patch(url, json={"schedule_minutes": 60}).json()["schedule_minutes"] == 60
    assert client.patch(url, json={"enabled": False}).json()["next_run_at"] is None
    assert client.post(f"{url}/run").status_code == 409  # disabled
    client.patch(url, json={"schedule_minutes": None})
    with factory() as session:  # an explicit null turns scheduling off
        assert session.scalar(select(func.count()).select_from(ScheduledTaskModel)) == 0
    assert client.delete(url).status_code == 204
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ScheduledTaskModel)) == 0
    assert client.delete(url).status_code == 404


def test_searches_are_scoped_to_their_profile(client: TestClient, world: dict[str, str]) -> None:
    search = create(client, world["a"], world["source"])
    other = f"/api/v1/profiles/{world['b']}/searches/{search['id']}"
    assert client.get(f"/api/v1/profiles/{world['b']}/searches").json() == []
    assert client.patch(other, json={"name": "x"}).status_code == 404
    assert client.post(f"{other}/run").status_code == 404
    assert client.get(f"{other}/runs").status_code == 404
    assert client.delete(other).status_code == 404
    assert client.get("/api/v1/profiles/nope/searches").status_code == 404


def test_validation(client: TestClient, world: dict[str, str]) -> None:
    base = f"/api/v1/profiles/{world['a']}/searches"
    assert client.post(base, json={"name": "x", "source_id": "nope"}).status_code == 422
    assert client.post(base, json={"name": "", "source_id": world["source"]}).status_code == 422
    assert client.post(base, json={"name": "x", "source_id": world["source"], "schedule_minutes": 1}).status_code == 422
    assert client.post("/api/v1/profiles/nope/searches", json={"name": "x", "source_id": world["source"]}).status_code == 404


# --- worker executes scheduled searches --------------------------------------------------------


def test_worker_runs_a_scheduled_search_and_records_outcome(factory: sessionmaker[Session], world: dict[str, str]) -> None:
    clock = Clock()
    clock.now = datetime.now(UTC)  # SearchService stamps real time when it creates the schedule
    with factory() as session:
        from careerflow.application.searches import SearchService

        search = SearchService(session).create(world["a"], {"name": "s", "source_id": world["source"], "schedule_minutes": 5, "filters_json": {}, "max_results": 10})
        search_id = search.id
        scheduler = SchedulerService(session, clock)
        clock.advance(5 * 60 + 1)
        (task,) = scheduler.tick()
        assert task.payload_json["search_id"] == search_id
    assert worker.run_one(factory, "w1", clock=clock) is True
    with factory() as session:
        done = session.get(TaskModel, task.id)
        assert done is not None and done.status == SUCCEEDED and done.metadata_json["created"] == 3
        schedule = session.scalars(select(ScheduledTaskModel)).one()
        assert schedule.last_status == "SUCCEEDED" and schedule.last_completed_at is not None
        runs = list(session.scalars(select(SearchRunModel)))
        assert len(runs) == 1 and runs[0].trigger == "schedule" and runs[0].created == 3


def test_failed_scheduled_search_fails_the_task_visibly(factory: sessionmaker[Session], world: dict[str, str]) -> None:
    clock = Clock()
    clock.now = datetime.now(UTC)
    with factory() as session:
        broken = JobSourceModel(name="broken", adapter="fixture", config_json={})
        session.add(broken)
        session.commit()
        from careerflow.application.searches import SearchService

        SearchService(session).create(world["a"], {"name": "s", "source_id": broken.id, "schedule_minutes": 5, "filters_json": {}, "max_results": 10})
        clock.advance(301)
        (task,) = SchedulerService(session, clock).tick()
        session.query(TaskModel).filter(TaskModel.id == task.id).update({"max_attempts": 1})
        session.commit()
    worker.run_one(factory, "w1", clock=clock)
    with factory() as session:
        failed = session.get(TaskModel, task.id)
        assert failed is not None and failed.status == FAILED
        assert failed.error_code == "RuntimeError" and "SourceConfigError" in (failed.error_message or "")
        assert session.scalars(select(ScheduledTaskModel)).one().last_status == "FAILED"
