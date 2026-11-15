"""Source ingestion pipeline: discover -> fetch -> normalize -> persist (plan section 9).

Each stage is independently testable. Cross-cutting policy lives here, not in adapters:
rate limiting from declared capabilities, retry with backoff for transient failures,
raw snapshot retention (JobSourceRecord.raw_payload), run history and health state.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobService
from careerflow.domain.jobs.fingerprint import job_fingerprint
from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    JobSourceAdapter,
    NormalizedJob,
    SourceConfigError,
    SourceError,
    SourceFetchError,
    SourceJobDocument,
    SourceJobReference,
    SourceRateLimitedError,
)
from careerflow.infrastructure.database.models import (
    JobModel,
    JobSourceModel,
    JobSourceRecordModel,
    SourceRunModel,
)
from careerflow.infrastructure.jobsources.http import HttpClient
from careerflow.infrastructure.jobsources.registry import build_adapter
from careerflow.infrastructure.logging import get_redactor, log_context

logger = logging.getLogger(__name__)

FAILING_AFTER = 3  # consecutive failed runs before a source is reported FAILING


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0


@dataclass
class IngestResult:
    discovered: int = 0
    created: list[JobModel] = field(default_factory=list)
    updated: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class RateLimiter:
    """Spaces calls so the source's declared requests-per-minute is never exceeded."""

    def __init__(self, per_minute: int | None, clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
        self.interval = 60.0 / per_minute if per_minute else 0.0
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self.interval and self._last is not None:
            remaining = self.interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


class IngestionService:
    def __init__(
        self,
        session: Session,
        http: HttpClient | None = None,
        retry: RetryPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        on_created: Callable[[JobModel], None] | None = None,
    ) -> None:
        self.session = session
        self.http = http
        self.retry = retry or RetryPolicy()
        self._clock, self._sleep = clock, sleep
        self.on_created = on_created
        self.jobs = JobService(session)

    # -- core pipeline -------------------------------------------------------------------

    def ingest(self, adapter: JobSourceAdapter, request: DiscoveryRequest | None = None) -> IngestResult:
        request = request or DiscoveryRequest()
        result = IngestResult()
        limiter = RateLimiter(adapter.capabilities.rate_limit_per_minute, self._clock, self._sleep)
        references = list(self._with_retry(lambda: list(adapter.discover(request)), limiter))
        result.discovered = len(references)
        for reference in references[: request.limit]:
            try:
                document = self._with_retry(partial(adapter.fetch, reference), limiter)
                normalized = adapter.normalize(document)
                job, created = self._persist(adapter.name, normalized, document)
            except SourceError as error:
                result.failed += 1
                result.errors.append(f"{reference.external_id}: {error}")
                logger.warning("source item failed", extra={"external_id": reference.external_id, "error": str(error)})
                continue
            if created:
                result.created.append(job)
            else:
                result.updated += 1
        for job in result.created:
            if self.on_created:
                self.on_created(job)
        return result

    def _with_retry[T](self, call: Callable[[], T], limiter: RateLimiter) -> T:
        for attempt in range(1, self.retry.max_attempts + 1):
            limiter.wait()
            try:
                return call()
            except SourceFetchError as error:
                if not error.retryable or attempt == self.retry.max_attempts:
                    raise
                delay = self.retry.base_delay_seconds * 2 ** (attempt - 1)
                if isinstance(error, SourceRateLimitedError) and error.retry_after_seconds:
                    delay = max(delay, error.retry_after_seconds)
                self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def _persist(
        self, adapter_name: str, job: NormalizedJob, document: SourceJobDocument
    ) -> tuple[JobModel, bool]:
        now = datetime.now(UTC)
        existing = self.session.scalars(
            select(JobSourceRecordModel).where(
                JobSourceRecordModel.adapter == adapter_name,
                JobSourceRecordModel.external_id == job.external_id,
            )
        ).first()
        if existing is not None:  # seen before: refresh the snapshot, never duplicate the job
            existing.raw_payload = document.raw_payload
            existing.source_url = job.source_url or existing.source_url
            existing.last_seen_at = now
            self.session.commit()
            return existing.job, False
        values: dict[str, Any] = {
            name: getattr(job, name)
            for name in (
                "title", "company", "description_text", "canonical_url", "company_domain",
                "description_html", "location_text", "remote_type", "employment_type",
                "salary_min", "salary_max", "salary_currency", "salary_period",
                "posted_at", "expires_at",
            )
        }  # fmt: skip
        values["status"] = "READY_FOR_REVIEW"
        values["raw_metadata_json"] = {"industry": job.industry} if job.industry else {}
        values["fingerprint"] = job_fingerprint(job.company, job.title, job.location_text)
        created = self.jobs.create_job(values)
        self.jobs.add_source_record(
            created.id,
            {
                "adapter": adapter_name,
                "external_id": job.external_id,
                "source_url": job.source_url,
                "raw_payload": document.raw_payload,
            },
        )
        for requirement in job.requirements:
            self.jobs.add_requirement(created.id, requirement)
        return created, True

    # -- configured sources -------------------------------------------------------------

    def run_source(
        self, source_id: str, trigger: str = "manual", request: DiscoveryRequest | None = None
    ) -> SourceRunModel:
        source = self.session.get(JobSourceModel, source_id)
        if source is None:
            raise LookupError(f"source not found: {source_id}")
        run = SourceRunModel(source_id=source.id, trigger=trigger, status="RUNNING", started_at=datetime.now(UTC))
        self.session.add(run)
        self.session.commit()
        with log_context(source_adapter=source.adapter):
            try:
                adapter = build_adapter(source.adapter, source.config_json, self.http)
                result = self.ingest(adapter, request)
            except SourceError as error:
                self._finish(source, run, "FAILED", error=error)
                logger.warning("source run failed", extra={"source": source.name, "error": str(error)})
            except Exception as error:  # a bug in an adapter must not take the worker down
                self._finish(source, run, "FAILED", error=error)
                logger.exception("source run crashed", extra={"source": source.name})
            else:
                run.discovered, run.created, run.updated, run.failed = (
                    result.discovered, len(result.created), result.updated, result.failed,
                )  # fmt: skip
                status = "SUCCEEDED" if not result.failed else "PARTIAL"
                last = result.errors[-1] if result.errors else None
                self._finish(source, run, status, message=last)
        return run

    def _finish(
        self,
        source: JobSourceModel,
        run: SourceRunModel,
        status: str,
        error: BaseException | None = None,
        message: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        run.status, run.finished_at = status, now
        if error is not None:
            run.error_code = type(error).__name__
            message = str(error)
        run.error_message = get_redactor().redact(message)[:2000] if message else None
        source.last_run_at, source.last_status = now, status
        source.last_error = run.error_message
        if status == "SUCCEEDED":
            source.consecutive_failures, source.health = 0, "HEALTHY"
        elif status == "PARTIAL":
            source.health = "DEGRADED"
        else:
            source.consecutive_failures += 1
            source.health = "FAILING" if source.consecutive_failures >= FAILING_AFTER else "DEGRADED"
        self.session.commit()


__all__ = ["IngestResult", "IngestionService", "RateLimiter", "RetryPolicy", "SourceConfigError", "SourceJobReference"]
