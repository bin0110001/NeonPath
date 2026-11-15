# CareerFlow

CareerFlow is a self-hosted job discovery, evaluation, and application-preparation platform. It automates organization and preparation while keeping people in control of external actions.

It works with no external services: AI, mailbox and calendar integrations are optional, and nothing is ever sent or written externally without your explicit approval.

**What you can do today**: keep several independent career profiles; import jobs by pasting text or from RSS/Atom, JSON and Greenhouse sources (on a schedule, per profile); see every job scored differently for each profile with explicit blockers and unknowns; review duplicates; move jobs through a per-profile workflow and pipeline board; get evidence-grounded tailoring and interview preparation; generate résumés as Markdown, HTML, DOCX or PDF; track applications, contacts, follow-ups and interviews with funnel metrics.

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

## Architecture and documentation

The backend keeps domain, application and infrastructure concerns separate; FastAPI is an inbound adapter, SQLAlchemy and PostgreSQL are infrastructure, and API schemas are separate from ORM models.

- [Architecture overview](docs/architecture/overview.md) and [diagram](docs/architecture/diagram.md)
- [Decision records](docs/adr/README.md) (ADR-001 to ADR-014)
- [API reference](docs/api/README.md) and [endpoint list](docs/api/endpoints.md)
- [How jobs are scored](docs/guides/scoring.md) · [profiles](docs/architecture/profiles.md) · [evaluation](docs/architecture/evaluation.md)
- Guides: [add a job source](docs/guides/write-a-job-source-adapter.md) · [add an LLM provider](docs/guides/write-an-llm-provider.md) · [Podman](docs/guides/podman.md) · [Docker Desktop](docs/guides/docker-desktop.md)
- [Privacy and security](docs/security/privacy.md) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## Status

The roadmap is in [careerflow_automation_implementation_plan.md](careerflow_automation_implementation_plan.md). All phases up to Phase 14 (artifact generation) are implemented; email and calendar integrations and the hosted-AI providers have been verified against recorded API responses only, not live services. See [release readiness](docs/release-readiness.md) for what remains before v1.0.0.

## License

MIT. See [LICENSE](LICENSE).

## Demo data

`python -m careerflow.seed` (run automatically by `backend/start.sh`) seeds two fictional profiles and four scenario jobs. It is idempotent: running it again changes nothing.
