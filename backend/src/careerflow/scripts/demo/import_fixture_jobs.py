"""Import fictional demo jobs from a JSON fixture.

Usage: python -m careerflow.scripts.demo.import_fixture_jobs <fixture.json>

Idempotent: a job whose canonical_url or title+company already exists is skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobService
from careerflow.infrastructure.database.models import JobModel
from careerflow.infrastructure.database.session import create_database_engine

JOB_KEYS = {
    "title", "company", "company_domain", "description_text", "description_html",
    "location_text", "remote_type", "employment_type", "salary_min", "salary_max",
    "salary_currency", "salary_period", "canonical_url", "raw_metadata_json",
}  # fmt: skip


def load_fixture_jobs(fixture_path: Path) -> list[dict[str, Any]]:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("fixture must be a JSON list of jobs")
    return [dict(item) for item in data]


def import_fixture_jobs(jobs_data: list[dict[str, Any]], session: Session) -> int:
    """Import jobs into ``session``; returns how many were created."""
    service = JobService(session)
    created = 0
    for item in jobs_data:
        title, company, url = item["title"], item["company"], item.get("canonical_url")
        duplicate = select(JobModel.id).where(
            ((JobModel.title == title) & (JobModel.company == company))
            | (JobModel.canonical_url == url if url else False)
        )
        if session.scalar(duplicate) is not None:
            print(f"Skipping existing job: {title} at {company}")
            continue
        values = {k: v for k, v in item.items() if k in JOB_KEYS}
        values["status"] = "READY_FOR_REVIEW"
        job = service.create_job(values)
        if item.get("source"):
            service.add_source_record(job.id, dict(item["source"]))
        for requirement in item.get("requirements", []):
            service.add_requirement(job.id, dict(requirement))
        created += 1
        print(f"Created job: {title} at {company}")
    return created


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m careerflow.scripts.demo.import_fixture_jobs <fixture.json>")
    fixture = Path(sys.argv[1])
    if not fixture.exists():
        raise SystemExit(f"Fixture file not found: {fixture}")
    jobs = load_fixture_jobs(fixture)
    with Session(create_database_engine()) as session:
        created = import_fixture_jobs(jobs, session)
    print(f"Imported {created} of {len(jobs)} jobs")


if __name__ == "__main__":
    main()
