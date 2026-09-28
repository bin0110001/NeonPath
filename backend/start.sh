#!/bin/sh
set -eu
uv run alembic upgrade head
uv run python -m careerflow.seed
exec uv run uvicorn careerflow.main:app --host 0.0.0.0 --port 8000
