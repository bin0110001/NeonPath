"""Background worker: ``python -m careerflow.worker``.

Polls the PostgreSQL task queue, runs registered handlers and records every outcome.
It shares the backend image with the API (plan section 23).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from careerflow.infrastructure.database.models import JobModel, TaskModel
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.infrastructure.logging import configure_logging, log_context, secrets_from_url
from careerflow.infrastructure.tasks.queue import TaskQueue
from careerflow.settings import get_settings

logger = logging.getLogger("careerflow.worker")

HEARTBEAT_FILE = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/careerflow-worker.heartbeat"))  # noqa: S108

Handler = Callable[[Session, TaskModel], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}


def handler(task_type: str) -> Callable[[Handler], Handler]:
    def register(func: Handler) -> Handler:
        HANDLERS[task_type] = func
        return func

    return register


@handler("noop")
def _noop(session: Session, task: TaskModel) -> dict[str, Any] | None:
    return {"echo": task.payload_json}


@handler("evaluate_job")
def _evaluate_job(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.evaluations.service import EvaluationService
    from careerflow.application.jobs.service import JobService
    from careerflow.application.profiles.service import ProfileService

    service = EvaluationService(JobService(session), ProfileService(session))
    job_id, profile_id = task.payload_json["job_id"], task.payload_json["profile_id"]
    row = service.evaluate_job_for_profile(job_id, profile_id)
    return {"evaluation_id": row.id, "overall_score": row.overall_score}


@handler("extract_requirements")
def _extract(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.ai.client import AiClient, RetryPolicy
    from careerflow.application.ai.requirements import RequirementExtractionService
    from careerflow.infrastructure.llm.factory import build_provider

    settings = get_settings()
    client = AiClient(build_provider(settings), retry=RetryPolicy(timeout_seconds=settings.ai_timeout_seconds))
    outcome = RequirementExtractionService(session, client).extract(task.payload_json["job_id"])
    return {"mode": outcome.mode, "count": len(outcome.requirements)}


@handler("run_source")
def _run_source(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.evaluations.service import EvaluationService
    from careerflow.application.jobs.service import JobService
    from careerflow.application.profiles.service import ProfileService
    from careerflow.application.sources.ingest import IngestionService

    evaluation = EvaluationService(JobService(session), ProfileService(session))

    def evaluate_new(job: JobModel) -> None:
        evaluation.evaluate_job_for_all_profiles(job.id)

    service = IngestionService(session, on_created=evaluate_new)
    run = service.run_source(task.payload_json["source_id"], trigger=task.payload_json.get("trigger", "task"))
    if run.status == "FAILED":  # surface failures on the task as well as on the source run
        raise RuntimeError(f"source run failed: {run.error_code}: {run.error_message}")
    return {"run_id": run.id, "status": run.status, "created": run.created, "updated": run.updated}


def run_one(factory: sessionmaker[Session], worker_id: str, **queue_options: Any) -> bool:
    """Claim and execute at most one task. Returns True if a task was processed."""
    with factory() as session:
        queue = TaskQueue(session, **queue_options)
        task = queue.claim(worker_id)
        if task is None:
            return False
        task_id, task_type = task.id, task.task_type
        with log_context(task_id=task_id, profile_id=task.profile_id):
            try:
                run = HANDLERS.get(task_type)
                if run is None:
                    raise LookupError(f"no handler registered for task type {task_type!r}")
                metadata = run(session, task) or {}
            except Exception as error:
                session.rollback()
                logger.exception("task failed", extra={"task_type": task_type})
                queue.fail(task, worker_id, error)
            else:
                queue.complete(task, worker_id, metadata)
                logger.info("task succeeded", extra={"task_type": task_type})
    return True


def run_worker(
    poll_interval: float = 2.0, stop: Event | None = None, worker_id: str | None = None
) -> None:
    stop = stop or Event()
    worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    factory = sessionmaker(create_database_engine(), expire_on_commit=False)
    settings = get_settings()
    logger.info("worker started", extra={"worker_id": worker_id})
    while not stop.is_set():
        try:
            HEARTBEAT_FILE.touch()
        except OSError:
            pass  # the health file is best-effort (read-only filesystems)
        try:
            worked = run_one(factory, worker_id, lease_seconds=settings.worker_lease_seconds)
        except Exception:  # database unreachable etc.: keep the process alive and retry
            logger.exception("worker loop error")
            worked = False
        if not worked:
            stop.wait(poll_interval)
    logger.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        secrets=[*settings.redact_value_list, *secrets_from_url(settings.database_url)],
    )
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_worker(settings.worker_poll_seconds, stop)


if __name__ == "__main__":
    main()
