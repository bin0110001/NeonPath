# Contributing

Use small vertical slices and preserve the backend boundaries: domain code must not depend on FastAPI, ORM entities must not be API responses, and external providers belong behind adapters.

Before opening a change, run backend tests/lint/type checking and frontend tests/lint/build. Keep the base `compose.yaml` portable across Podman and Docker; do not add privileged containers or engine-socket mounts.

Use fictional or redacted data only in committed fixtures and documentation.

## Database migrations

- Never edit a migration that has been merged; add a new revision.
- After changing `infrastructure/database/models.py`, generate it: `cd backend && uv run alembic revision --autogenerate -m "describe change"`, then review and edit the result. Never call `Base.metadata.create_all` in a revision.
- Drift check (models vs. migrations, needs a PostgreSQL at `DATABASE_URL`): `uv run alembic upgrade head && uv run alembic check`.
- Round trip: `alembic upgrade head && alembic downgrade base && alembic upgrade head`. CI runs both checks.
- Databases created before ADR-013 must be reset (`compose down -v`).
