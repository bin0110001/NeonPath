# CareerFlow

CareerFlow is a self-hosted job discovery, evaluation, and application-preparation platform. It automates organization and preparation while keeping people in control of external actions.

This repository currently implements Phase 0: a runnable monorepo foundation. Profile, job, and AI workflows intentionally come in later vertical slices.

## Start locally

Copy the environment defaults, then start with either compatible Compose implementation:

```sh
cp .env.example .env
podman compose up -d --build
# or: docker compose up -d --build
```

Open the web shell at `http://localhost:5173`. The API is at `http://localhost:8000`; liveness and readiness are available at `/health/live` and `/health/ready`.

The supplied database password is for local development only. Change it before exposing a deployment.

## Development and verification

Backend commands (requires Python 3.13+ and [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy src
```

Frontend commands (requires Node 22+):

```sh
cd frontend
npm install
npm run test
npm run lint
npm run build
```

For API hot reload, use `podman compose -f compose.yaml -f compose.dev.yaml up --build` (or Docker Compose). Run `npm run dev` in `frontend/` for frontend hot reload.

## Architecture

The backend keeps domain, application, and infrastructure concerns separate. FastAPI is an inbound adapter; SQLAlchemy and PostgreSQL are infrastructure. Future API response schemas will remain separate from ORM models. See [architecture overview](docs/architecture/overview.md).

## Status

The plan is tracked in [careerflow_automation_implementation_plan.md](careerflow_automation_implementation_plan.md). Phase 0 is implemented; future work should proceed as coherent vertical slices, beginning with Profile Core.

## License

MIT. See [LICENSE](LICENSE).
