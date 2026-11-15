"""Persisted schedules and the scheduler tick (plan section 18).

``tick`` is safe to run in several processes at once: due schedules are claimed with
``SELECT ... FOR UPDATE SKIP LOCKED``, advanced and committed in the same transaction as
the enqueue, so each occurrence is enqueued exactly once. If the previous occurrence is
still queued or running, the new one is skipped (no pile-up) and the schedule moves on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import ScheduledTaskModel, TaskModel
from careerflow.infrastructure.tasks.queue import QUEUED, RUNNING, utc_now

logger = logging.getLogger(__name__)

MAINTENANCE_SCHEDULES: tuple[tuple[str, str, int], ...] = (
    # key, task type, interval seconds
    ("maintenance:expiration", "check_expiration", 6 * 3600),
    ("maintenance:prune", "prune_raw_payloads", 24 * 3600),
)


class SchedulerService:
    def __init__(self, session: Session, clock: Callable[[], datetime] = utc_now) -> None:
        self.session = session
        self.clock = clock

    def upsert(
        self,
        key: str,
        task_type: str,
        interval_seconds: int,
        payload: dict[str, Any] | None = None,
        profile_id: str | None = None,
        enabled: bool = True,
    ) -> ScheduledTaskModel:
        """Create or update the schedule for ``key``; changing the interval reschedules it."""
        row = self.session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.key == key)).first()
        now = self.clock()
        if row is None:
            row = ScheduledTaskModel(
                key=key, task_type=task_type, profile_id=profile_id, payload_json=payload or {},
                interval_seconds=interval_seconds, enabled=enabled,
                next_run_at=now + timedelta(seconds=interval_seconds),
            )  # fmt: skip
            self.session.add(row)
        else:
            if row.interval_seconds != interval_seconds:
                row.next_run_at = now + timedelta(seconds=interval_seconds)
            row.task_type, row.profile_id = task_type, profile_id
            row.payload_json = payload or {}
            row.interval_seconds, row.enabled = interval_seconds, enabled
        self.session.commit()
        self.session.refresh(row)
        return row

    def remove(self, key: str) -> None:
        row = self.session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.key == key)).first()
        if row is not None:
            self.session.delete(row)
            self.session.commit()

    def ensure_maintenance_schedules(self) -> None:
        """Idempotently register the built-in housekeeping schedules (never resets timers)."""
        for key, task_type, interval in MAINTENANCE_SCHEDULES:
            exists = self.session.scalars(select(ScheduledTaskModel.id).where(ScheduledTaskModel.key == key)).first()
            if exists is None:
                self.upsert(key, task_type, interval)

    def tick(self) -> list[TaskModel]:
        """Enqueue every due schedule once. Returns the tasks that were enqueued."""
        now = self.clock()
        enqueued: list[TaskModel] = []
        due = self.session.scalars(
            select(ScheduledTaskModel)
            .where(ScheduledTaskModel.enabled.is_(True), ScheduledTaskModel.next_run_at <= now)
            .order_by(ScheduledTaskModel.next_run_at)
            .with_for_update(skip_locked=True)
        ).all()
        for schedule in due:
            schedule.next_run_at = now + timedelta(seconds=schedule.interval_seconds)
            if self._still_active(schedule):
                logger.warning("schedule skipped: previous run still active", extra={"schedule": schedule.key})
                continue
            task = TaskModel(
                task_type=schedule.task_type,
                profile_id=schedule.profile_id,
                payload_json={**schedule.payload_json, "trigger": "schedule", "schedule_key": schedule.key},
                run_after=now,
                created_at=now,
                status=QUEUED,
            )
            self.session.add(task)
            self.session.flush()
            schedule.last_task_id, schedule.last_started_at = task.id, now
            enqueued.append(task)
        self.session.commit()
        return enqueued

    def _still_active(self, schedule: ScheduledTaskModel) -> bool:
        if not schedule.last_task_id:
            return False
        previous = self.session.get(TaskModel, schedule.last_task_id)
        return previous is not None and previous.status in (QUEUED, RUNNING)

    def record_outcome(self, schedule_key: str, status: str) -> None:
        """Called by the worker when a scheduled occurrence finishes."""
        row = self.session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.key == schedule_key)).first()
        if row is not None:
            row.last_completed_at, row.last_status = self.clock(), status
            self.session.commit()
