#!/bin/sh
set -eu
# Wait for the database (and the engine's own healthcheck is not required to be supported).
i=0
until uv run alembic current >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -ge 60 ] && { echo "database not reachable after 60s" >&2; exit 1; }
  sleep 1
done
uv run alembic upgrade head
uv run python -m careerflow.seed
exec uv run uvicorn careerflow.main:app --host 0.0.0.0 --port 8000
