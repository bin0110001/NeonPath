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

from careerflow.application.scheduling import SchedulerService
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
    from careerflow.application.ai.config import build_client
    from careerflow.application.ai.requirements import RequirementExtractionService

    outcome = RequirementExtractionService(session, build_client(session)).extract(task.payload_json["job_id"])
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


@handler("run_search")
def _run_search(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.searches import SearchService

    run = SearchService(session).run(task.payload_json["search_id"], task.payload_json.get("trigger", "task"))
    if run.status == "FAILED":
        raise RuntimeError(f"search run failed: {run.error_code}: {run.error_message}")
    return {"search_run_id": run.id, "status": run.status, "created": run.created, "failed": run.failed}


@handler("check_expiration")
def _check_expiration(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.maintenance import MaintenanceService

    report = MaintenanceService(session).check_expiration(get_settings().listing_stale_days)
    return {"expired": report.expired, "revived": report.revived}


@handler("prune_raw_payloads")
def _prune(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.maintenance import MaintenanceService

    return {"pruned": MaintenanceService(session).prune_raw_payloads(get_settings().raw_payload_retention_days)}


@handler("reevaluate_profile")
def _reevaluate(session: Session, task: TaskModel) -> dict[str, Any] | None:
    from careerflow.application.maintenance import MaintenanceService

    return {"jobs": MaintenanceService(session).reevaluate_profile(task.payload_json["profile_id"])}


def _record_schedule(session: Session, task: TaskModel, status: str) -> None:
    from careerflow.application.scheduling import SchedulerService

    key = (task.payload_json or {}).get("schedule_key")
    if key and (status == "SUCCEEDED" or task.status == "FAILED"):  # final outcomes only
        SchedulerService(session).record_outcome(str(key), status)


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
                _record_schedule(session, task, "FAILED")
            else:
                queue.complete(task, worker_id, metadata)
                logger.info("task succeeded", extra={"task_type": task_type})
                _record_schedule(session, task, "SUCCEEDED")
    return True


def run_worker(
    poll_interval: float = 2.0, stop: Event | None = None, worker_id: str | None = None
) -> None:
    stop = stop or Event()
    worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    factory = sessionmaker(create_database_engine(), expire_on_commit=False)
    settings = get_settings()
    logger.info("worker started", extra={"worker_id": worker_id})
    schedules_ready = False
    while not stop.is_set():
        if not schedules_ready:
            try:  # the API may still be migrating the database: retry instead of exiting
                with factory() as session:
                    SchedulerService(session).ensure_maintenance_schedules()
                schedules_ready = True
            except Exception:
                logger.warning("database not ready for the worker yet; retrying")
                stop.wait(poll_interval)
                continue
        try:
            HEARTBEAT_FILE.touch()
        except OSError:
            pass  # the health file is best-effort (read-only filesystems)
        try:
            with factory() as session:
                SchedulerService(session).tick()  # enqueue due schedules (exactly once, row-locked)
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
