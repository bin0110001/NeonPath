"""Import fictional demo jobs from a JSON fixture through the FixtureJobAdapter.

Usage: python -m careerflow.scripts.demo.import_fixture_jobs <fixture.json>

Idempotent: jobs already ingested from the same fixture (same external id) are refreshed,
never duplicated.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from careerflow.application.sources.ingest import IngestionService
from careerflow.domain.sources.ports import SourceError
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.infrastructure.jobsources.simple import FixtureJobAdapter


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m careerflow.scripts.demo.import_fixture_jobs <fixture.json>")
    fixture = Path(sys.argv[1])
    if not fixture.exists():
        raise SystemExit(f"Fixture file not found: {fixture}")
    try:
        adapter = FixtureJobAdapter({"path": str(fixture)})
        with Session(create_database_engine()) as session:
            result = IngestionService(session).ingest(adapter)
    except SourceError as error:
        raise SystemExit(f"Import failed: {error}") from error
    print(f"Discovered {result.discovered}: created {len(result.created)}, updated {result.updated}, failed {result.failed}")
    for message in result.errors:
        print(f"  error: {message}")


if __name__ == "__main__":
    main()
