"""Demo mode: external-write guard and the reset-to-known-state command.

``python -m careerflow.demo reset`` drops every row and reseeds the fictional demo data.
It refuses to run unless ``DEMO_MODE=true`` so a real database cannot be wiped by accident.
"""

from __future__ import annotations

import sys

from sqlalchemy import delete
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import Base
from careerflow.infrastructure.database.session import create_database_engine
from careerflow.seed import seed_session
from careerflow.settings import Settings, get_settings


class DemoModeRequiredError(Exception):
    pass


class ExternalWritesDisabledError(Exception):
    """Raised when an integration tries to write to an external system in demo mode."""


def external_writes_allowed(settings: Settings | None = None) -> bool:
    return not (settings or get_settings()).demo_mode


def ensure_external_writes_allowed(settings: Settings | None = None) -> None:
    """Shared guard for every integration that changes something outside CareerFlow
    (sending e-mail, creating calendar events, ...). Call it before the write."""
    if not external_writes_allowed(settings):
        raise ExternalWritesDisabledError("external writes are disabled in demo mode")


def reset_demo_data(session: Session, settings: Settings | None = None) -> None:
    """Delete all data and reseed the known demo state."""
    if not (settings or get_settings()).demo_mode:
        raise DemoModeRequiredError("reset requires DEMO_MODE=true")
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(delete(table))
    session.commit()
    seed_session(session)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args != ["reset"]:
        print("usage: python -m careerflow.demo reset", file=sys.stderr)
        return 2
    try:
        with Session(create_database_engine()) as session:
            reset_demo_data(session)
    except DemoModeRequiredError as error:
        print(f"refusing to reset: {error}", file=sys.stderr)
        return 1
    print("demo data reset to the seeded state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
