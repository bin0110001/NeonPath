from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.session import create_database_engine
from careerflow.infrastructure.tasks.queue import STATUSES, TaskQueue
from careerflow.worker import HANDLERS

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_session() -> Generator[Session]:
    with Session(create_database_engine()) as session:
        yield session


class TaskOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_type: str
    profile_id: str | None
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    metadata_json: dict[str, Any]
    payload_json: dict[str, Any]


class TaskCreate(BaseModel):
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    profile_id: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)


@router.get("", response_model=list[TaskOutput])
def list_tasks(
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[TaskOutput]:
    """Recent tasks, newest first. ``?status=FAILED`` lists failures with their error."""
    if status_ is not None and status_ not in STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"status must be one of {STATUSES}")
    return [TaskOutput.model_validate(t) for t in TaskQueue(session).list(status_, limit)]


@router.post("", response_model=TaskOutput, status_code=status.HTTP_201_CREATED)
def enqueue_task(payload: TaskCreate, session: Session = Depends(get_session)) -> TaskOutput:
    if payload.task_type not in HANDLERS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown task type; known: {sorted(HANDLERS)}",
        )
    task = TaskQueue(session).enqueue(
        payload.task_type, payload.payload, payload.profile_id, payload.max_attempts
    )
    return TaskOutput.model_validate(task)


@router.post("/{task_id}/retry", response_model=TaskOutput)
def retry_task(task_id: str, session: Session = Depends(get_session)) -> TaskOutput:
    task = TaskQueue(session).retry(task_id)
    if task is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="only existing FAILED tasks can be retried")
    return TaskOutput.model_validate(task)
