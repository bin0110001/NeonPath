"""Search definitions (plan section 17): profile-scoped, source-independent, schedulable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileNotFoundError, ProfileService
from careerflow.application.scheduling import SchedulerService
from careerflow.application.sources.ingest import IngestionService
from careerflow.domain.sources.ports import DiscoveryRequest, NormalizedJob
from careerflow.infrastructure.database.models import (
    JobModel,
    JobSourceModel,
    ProfileModel,
    SearchDefinitionModel,
    SearchRunModel,
    SourceRunModel,
)
from careerflow.infrastructure.jobsources.http import HttpClient


class SearchNotFoundError(Exception):
    pass


class SearchConfigError(Exception):
    pass


def schedule_key(search_id: str) -> str:
    return f"search:{search_id}"


def make_filter(filters: dict[str, Any]) -> Any:
    """Build the ``accept`` predicate from ``keywords_any`` / ``exclude_keywords`` filters."""
    include = [str(k).lower() for k in filters.get("keywords_any", []) if str(k).strip()]
    exclude = [str(k).lower() for k in filters.get("exclude_keywords", []) if str(k).strip()]
    remote = filters.get("remote_type")
    if not (include or exclude or remote):
        return None

    def accept(job: NormalizedJob) -> bool:
        text = f"{job.title}\n{job.description_text}".lower()
        if include and not any(k in text for k in include):
            return False
        if exclude and any(k in text for k in exclude):
            return False
        return not (remote and (job.remote_type or "").upper() != str(remote).upper())

    return accept


class SearchService:
    def __init__(self, session: Session, http: HttpClient | None = None) -> None:
        self.session = session
        self.http = http

    # -- definitions -----------------------------------------------------------------------

    def _check(self, profile_id: str, source_id: str) -> None:
        if self.session.get(ProfileModel, profile_id) is None:
            raise ProfileNotFoundError(profile_id)
        if self.session.get(JobSourceModel, source_id) is None:
            raise SearchConfigError("source not found")

    def get(self, profile_id: str, search_id: str) -> SearchDefinitionModel:
        """Profile-scoped lookup: another profile's search is reported as missing."""
        row = self.session.get(SearchDefinitionModel, search_id)
        if row is None or row.profile_id != profile_id:
            raise SearchNotFoundError(search_id)
        return row

    def list_for_profile(self, profile_id: str) -> list[SearchDefinitionModel]:
        if self.session.get(ProfileModel, profile_id) is None:
            raise ProfileNotFoundError(profile_id)
        return list(
            self.session.scalars(
                select(SearchDefinitionModel)
                .where(SearchDefinitionModel.profile_id == profile_id)
                .order_by(SearchDefinitionModel.name)
            )
        )

    def create(self, profile_id: str, values: dict[str, Any]) -> SearchDefinitionModel:
        self._check(profile_id, values["source_id"])
        row = SearchDefinitionModel(profile_id=profile_id, **values)
        self.session.add(row)
        self.session.commit()
        self._sync_schedule(row)
        return row

    def update(self, profile_id: str, search_id: str, values: dict[str, Any]) -> SearchDefinitionModel:
        row = self.get(profile_id, search_id)
        if "source_id" in values:
            self._check(profile_id, values["source_id"])
        for name, value in values.items():
            setattr(row, name, value)
        self.session.commit()
        self._sync_schedule(row)
        return row

    def delete(self, profile_id: str, search_id: str) -> None:
        row = self.get(profile_id, search_id)
        SchedulerService(self.session).remove(schedule_key(row.id))
        for run in self.session.scalars(select(SearchRunModel).where(SearchRunModel.search_id == row.id)):
            self.session.delete(run)
        self.session.delete(row)
        self.session.commit()

    def _sync_schedule(self, row: SearchDefinitionModel) -> None:
        scheduler = SchedulerService(self.session)
        if row.schedule_minutes:
            scheduler.upsert(
                schedule_key(row.id),
                "run_search",
                row.schedule_minutes * 60,
                {"search_id": row.id},
                profile_id=row.profile_id,
                enabled=row.enabled,
            )
        else:
            scheduler.remove(schedule_key(row.id))

    # -- running ---------------------------------------------------------------------------

    def run(self, search_id: str, trigger: str = "manual") -> SearchRunModel:
        """Run the search through its source; new jobs are evaluated for the owning profile only."""
        search = self.session.get(SearchDefinitionModel, search_id)
        if search is None:
            raise SearchNotFoundError(search_id)
        run = SearchRunModel(search_id=search.id, trigger=trigger, started_at=datetime.now(UTC))
        self.session.add(run)
        self.session.commit()

        evaluation = EvaluationService(JobService(self.session), ProfileService(self.session))

        def evaluate_for_owner(job: JobModel) -> None:
            evaluation.evaluate_job_for_profile(job.id, search.profile_id)

        ingestion = IngestionService(self.session, http=self.http, on_created=evaluate_for_owner)
        request = DiscoveryRequest(query=search.query, location=search.location, limit=search.max_results)
        source_run = ingestion.run_source(search.source_id, trigger, request, make_filter(search.filters_json))
        self._finish(search, run, source_run)
        return run

    def _finish(self, search: SearchDefinitionModel, run: SearchRunModel, source_run: SourceRunModel) -> None:
        now = datetime.now(UTC)
        run.source_run_id = source_run.id
        run.status = source_run.status
        run.finished_at = now
        run.discovered, run.created, run.updated, run.failed = (
            source_run.discovered, source_run.created, source_run.updated, source_run.failed,
        )  # fmt: skip
        run.skipped = source_run.skipped
        run.error_code, run.error_message = source_run.error_code, source_run.error_message
        search.last_run_at = now
        self.session.commit()

    def runs(self, profile_id: str, search_id: str, limit: int = 20) -> list[SearchRunModel]:
        self.get(profile_id, search_id)
        return list(
            self.session.scalars(
                select(SearchRunModel)
                .where(SearchRunModel.search_id == search_id)
                .order_by(SearchRunModel.started_at.desc())
                .limit(limit)
            )
        )
