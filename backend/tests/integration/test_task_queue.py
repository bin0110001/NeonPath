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
from careerflow.api.tasks import get_session
from careerflow.infrastructure.database.models import Base, TaskModel
from careerflow.infrastructure.tasks.queue import FAILED, QUEUED, RUNNING, SUCCEEDED, TaskQueue
from careerflow.main import create_app

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


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


def test_claim_runs_task_once_and_records_success(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        queue = TaskQueue(session, clock=clock, lease_seconds=30)
        queue.enqueue("noop", {"x": 1})
        task = queue.claim("w1")
        assert task is not None and task.status == RUNNING and task.attempts == 1
        assert task.lease_owner == "w1"
        assert queue.claim("w2") is None  # leased: nobody else can take it
        assert queue.complete(task, "w1", {"done": True})
        done = session.get(TaskModel, task.id)
        assert done is not None
        assert done.status == SUCCEEDED and done.metadata_json == {"done": True}
        assert done.lease_owner is None and done.completed_at is not None
        assert queue.claim("w1") is None


def test_expired_lease_is_taken_over(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        queue = TaskQueue(session, clock=clock, lease_seconds=30)
        queue.enqueue("noop")
        first = queue.claim("w1")
        assert first is not None
        clock.advance(31)
        second = queue.claim("w2")
        assert second is not None and second.id == first.id
        assert second.attempts == 2 and second.lease_owner == "w2"
        # the original worker finishing late must not overwrite the new owner's result
        assert not queue.complete(first, "w1")
        assert queue.heartbeat(second, "w2")
        assert queue.complete(second, "w2")


def test_dead_worker_on_last_attempt_ends_failed(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        queue = TaskQueue(session, clock=clock, lease_seconds=10)
        task = queue.enqueue("noop", max_attempts=1)
        assert queue.claim("w1") is not None
        clock.advance(11)
        assert queue.claim("w2") is None
        done = session.get(TaskModel, task.id)
        assert done is not None
        assert done.status == FAILED and done.error_code == "lease_expired"


def test_failure_retries_with_exponential_backoff_then_fails(factory: sessionmaker[Session]) -> None:
    clock = Clock()
    with factory() as session:
        queue = TaskQueue(session, clock=clock, backoff_base_seconds=5)
        task = queue.enqueue("noop", max_attempts=3)
        for attempt, delay in ((1, 5), (2, 10)):
            claimed = queue.claim("w")
            assert claimed is not None and claimed.attempts == attempt
            assert queue.fail(claimed, "w", RuntimeError(f"boom {attempt}"))
            session.refresh(task)
            assert task.status == QUEUED and task.error_message == f"boom {attempt}"
            assert queue.claim("w") is None  # still backing off
            clock.advance(delay)
        last = queue.claim("w")
        assert last is not None and last.attempts == 3
        queue.fail(last, "w", ValueError("final"))
        session.refresh(task)
        assert task.status == FAILED
        assert (task.error_code, task.error_message) == ("ValueError", "final")
        assert task.completed_at is not None
        assert queue.claim("w") is None

        retried = queue.retry(task.id)
        assert retried is not None and retried.status == QUEUED and retried.attempts == 0
        assert queue.retry(task.id) is None  # only FAILED tasks can be retried


def test_error_messages_are_redacted(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        queue = TaskQueue(session)
        task = queue.enqueue("noop", max_attempts=1)
        claimed = queue.claim("w")
        assert claimed is not None
        queue.fail(claimed, "w", RuntimeError("call failed: api_key=supersecretvalue1 for a@b.com"))
        session.refresh(task)
        assert "supersecretvalue1" not in (task.error_message or "")
        assert "a@b.com" not in (task.error_message or "")


def test_worker_runs_handlers_and_records_unknown_types_as_failures(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        queue = TaskQueue(session)
        ok = queue.enqueue("noop", {"hello": "world"})
        bad = queue.enqueue("does_not_exist", max_attempts=1)
    assert worker.run_one(factory, "w1") is True
    assert worker.run_one(factory, "w1") is True
    assert worker.run_one(factory, "w1") is False
    with factory() as session:
        done, failed = session.get(TaskModel, ok.id), session.get(TaskModel, bad.id)
        assert done is not None and failed is not None
        assert done.status == SUCCEEDED and done.metadata_json == {"echo": {"hello": "world"}}
        assert failed.status == FAILED and failed.error_code == "LookupError"
        assert "does_not_exist" in (failed.error_message or "")


def test_handler_exception_is_never_swallowed(factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(session: Session, task: TaskModel) -> None:
        raise ZeroDivisionError("kaboom")

    monkeypatch.setitem(worker.HANDLERS, "explode", explode)
    with factory() as session:
        task = TaskQueue(session).enqueue("explode", max_attempts=1)
    worker.run_one(factory, "w1")
    with factory() as session:
        row = session.get(TaskModel, task.id)
        assert row is not None and row.status == FAILED and row.error_code == "ZeroDivisionError"


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Generator[TestClient]:
    app = create_app()

    def override() -> Generator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)


def test_api_lists_failed_tasks_with_their_error(client: TestClient, factory: sessionmaker[Session]) -> None:
    assert client.post("/api/v1/tasks", json={"task_type": "nope"}).status_code == 422
    created = client.post("/api/v1/tasks", json={"task_type": "noop", "max_attempts": 1})
    assert created.status_code == 201
    with factory() as session:
        queue = TaskQueue(session)
        claimed = queue.claim("w")
        assert claimed is not None
        queue.fail(claimed, "w", RuntimeError("provider exploded"))
    failed = client.get("/api/v1/tasks", params={"status": "FAILED"}).json()
    assert [t["id"] for t in failed] == [created.json()["id"]]
    assert failed[0]["error_code"] == "RuntimeError" and failed[0]["error_message"] == "provider exploded"
    assert client.get("/api/v1/tasks", params={"status": "bogus"}).status_code == 422
    retried = client.post(f"/api/v1/tasks/{failed[0]['id']}/retry")
    assert retried.status_code == 200 and retried.json()["status"] == "QUEUED"
    assert client.post(f"/api/v1/tasks/{failed[0]['id']}/retry").status_code == 409


POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_DATABASE_URL to a PostgreSQL database")
def test_two_workers_never_run_the_same_task() -> None:
    assert POSTGRES_URL
    engine = create_engine(POSTGRES_URL, pool_size=10)
    Base.metadata.create_all(engine)  # full schema: task tables have foreign keys to profiles
    with sessionmaker(engine)() as cleanup:  # empty the queue tables; the schema itself is shared
        cleanup.execute(delete(TaskModel))
        cleanup.commit()
    factory = sessionmaker(engine, expire_on_commit=False)
    total = 40
    with factory() as session:
        queue = TaskQueue(session)
        for i in range(total):
            queue.enqueue("noop", {"n": i})

    claimed: list[tuple[str, str]] = []
    lock = threading.Lock()

    def work(worker_id: str) -> None:
        with factory() as session:
            queue = TaskQueue(session, lease_seconds=300)
            while (task := queue.claim(worker_id)) is not None:
                with lock:
                    claimed.append((worker_id, task.id))
                queue.complete(task, worker_id)

    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = [task_id for _, task_id in claimed]
    assert len(ids) == total and len(set(ids)) == total  # each task claimed exactly once
    assert len({w for w, _ in claimed}) > 1  # work really was shared
    with factory() as session:
        done = session.scalar(select(func.count()).select_from(TaskModel).where(TaskModel.status == SUCCEEDED))
        assert done == total
        attempts = session.scalars(select(TaskModel.attempts)).all()
        assert set(attempts) == {1}
    with sessionmaker(engine)() as cleanup:
        cleanup.execute(delete(TaskModel))
        cleanup.commit()
