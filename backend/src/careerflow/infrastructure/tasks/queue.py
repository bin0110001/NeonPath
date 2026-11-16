"""PostgreSQL-backed task queue with leases (no Redis needed, plan section 3).

Claiming uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent workers never take
the same task. A running task holds a lease; if its worker dies the lease expires and
another worker picks it up (counting as another attempt). Failures are always recorded
on the task, never swallowed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import TaskModel
from careerflow.infrastructure.logging import get_redactor

logger = logging.getLogger(__name__)

QUEUED, RUNNING, SUCCEEDED, FAILED = "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"
STATUSES = (QUEUED, RUNNING, SUCCEEDED, FAILED)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskQueue:
    def __init__(
        self,
        session: Session,
        clock: Clock = utc_now,
        lease_seconds: float = 60.0,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        self.session = session
        self.clock = clock
        self.lease_seconds = lease_seconds
        self.backoff_base_seconds = backoff_base_seconds

    def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any] | None = None,
        profile_id: str | None = None,
        max_attempts: int = 3,
        run_after: datetime | None = None,
    ) -> TaskModel:
        task = TaskModel(
            task_type=task_type,
            payload_json=payload or {},
            profile_id=profile_id,
            max_attempts=max_attempts,
            run_after=run_after or self.clock(),
            created_at=self.clock(),
            status=QUEUED,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def claim(self, worker_id: str) -> TaskModel | None:
        """Atomically lease the next runnable task, or return None."""
        now = self.clock()
        while True:
            runnable = or_(
                and_(TaskModel.status == QUEUED, TaskModel.run_after <= now),
                and_(TaskModel.status == RUNNING, TaskModel.lease_expires_at < now),
            )
            statement = (
                select(TaskModel)
                .where(runnable)
                .order_by(TaskModel.run_after, TaskModel.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            task = self.session.scalars(statement).first()
            if task is None:
                self.session.rollback()
                return None
            if task.status == RUNNING and task.attempts >= task.max_attempts:
                # The worker died on its last attempt: give up rather than loop forever.
                self._finish_failed(task, "lease_expired", "worker stopped without finishing", now)
                self.session.commit()
                continue
            task.status = RUNNING
            task.attempts += 1
            task.lease_owner = worker_id
            task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            task.started_at = now
            self.session.commit()
            self.session.refresh(task)
            return task

    def heartbeat(self, task: TaskModel, worker_id: str) -> bool:
        """Extend the lease of a long task. False if the lease was lost."""
        self.session.refresh(task)
        if task.status != RUNNING or task.lease_owner != worker_id:
            return False
        task.lease_expires_at = self.clock() + timedelta(seconds=self.lease_seconds)
        self.session.commit()
        return True

    def complete(self, task: TaskModel, worker_id: str, metadata: dict[str, Any] | None = None) -> bool:
        self.session.refresh(task)
        if task.status != RUNNING or task.lease_owner != worker_id:
            logger.warning("task %s finished after losing its lease; result ignored", task.id)
            return False
        task.status = SUCCEEDED
        task.completed_at = self.clock()
        task.lease_owner = task.lease_expires_at = None
        task.error_code = task.error_message = None
        task.metadata_json = metadata or {}
        self.session.commit()
        return True

    def fail(self, task: TaskModel, worker_id: str, error: BaseException) -> bool:
        """Record the error; requeue with exponential backoff unless attempts are exhausted."""
        self.session.refresh(task)
        if task.status != RUNNING or task.lease_owner != worker_id:
            logger.warning("task %s failed after losing its lease; error ignored", task.id)
            return False
        now = self.clock()
        code = type(error).__name__
        message = get_redactor().redact(str(error))[:2000]
        if task.attempts < task.max_attempts:
            task.status = QUEUED
            task.run_after = now + timedelta(seconds=self.backoff_base_seconds * 2 ** (task.attempts - 1))
            task.lease_owner = task.lease_expires_at = None
            task.error_code, task.error_message = code, message
        else:
            self._finish_failed(task, code, message, now)
        self.session.commit()
        return True

    def _finish_failed(self, task: TaskModel, code: str, message: str, now: datetime) -> None:
        task.status = FAILED
        task.completed_at = now
        task.lease_owner = task.lease_expires_at = None
        task.error_code, task.error_message = code, message

    def retry(self, task_id: str) -> TaskModel | None:
        """Manually requeue a FAILED task with a fresh attempt budget."""
        task = self.session.get(TaskModel, task_id)
        if task is None or task.status != FAILED:
            return None
        task.status = QUEUED
        task.attempts = 0
        task.run_after = self.clock()
        task.completed_at = None
        self.session.commit()
        self.session.refresh(task)
        return task

    def list(self, status: str | None = None, limit: int = 100) -> list[TaskModel]:
        statement = select(TaskModel).order_by(TaskModel.created_at.desc()).limit(limit)
        if status:
            statement = statement.where(TaskModel.status == status)
        return list(self.session.scalars(statement))
