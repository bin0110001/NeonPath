# Architecture overview

CareerFlow is a monorepo: a React web client, a Python API and worker (one backend image, different commands) and PostgreSQL. The Compose file uses only the current Compose Specification, named volumes and unprivileged services, so it runs unchanged under Podman and Docker. See the [diagram](diagram.md) for the moving parts.

## Layers (backend)

| Layer | Path | Responsibility | May depend on |
|---|---|---|---|
| Domain | `backend/src/careerflow/domain` | Business rules as pure code: workflow state machine, deterministic evaluation, deduplication, tailoring, metrics, ports for AI / sources / integrations / artifacts | nothing outside the domain |
| Application | `.../application` | Use cases that coordinate domain and persistence: ingestion, evaluation services, tracking, scheduling, maintenance | domain, infrastructure |
| Infrastructure | `.../infrastructure` | SQLAlchemy models, task queue, LLM / job-source / integration / renderer adapters, logging, encryption | domain |
| API | `.../api` | FastAPI routes and Pydantic schemas; no business logic, ORM rows are never returned directly | application |

Rules that are enforced by tests: the domain imports no FastAPI, SQLAlchemy or LLM SDK; nothing in the code base can send email; profile-owned records are only reachable through their profile ([ADR-005](../adr/ADR-005-profile-scoped-domain-model.md)).

## Processes

- **API** (`uvicorn careerflow.main:app`): runs migrations and the idempotent demo seed on start, serves `/api/v1`, `/health/live`, `/health/ready`.
- **Worker** (`python -m careerflow.worker`): claims tasks from a PostgreSQL queue with `FOR UPDATE SKIP LOCKED` and leases, runs registered handlers (search runs, requirement extraction, re-evaluation, maintenance) and enqueues due schedules. Failures are stored on the task and shown in the UI.
- **Web**: static React build served by nginx.

## Main flows

1. **Ingest**: a source adapter (`manual`, `fixture`, `rss`, `generic_json`, `greenhouse`) discovers, fetches and normalises postings into canonical jobs; raw payloads are kept per source record; exact duplicates attach to the existing job, probable ones go to a review queue ([ADR-006](../adr/ADR-006-source-adapter-architecture.md)).
2. **Evaluate**: the deterministic evaluator scores each job per profile with explicit blockers and unknowns; optional AI adds evidence-linked claims on top ([evaluation](evaluation.md), [scoring guide](../guides/scoring.md), [ADR-011](../adr/ADR-011-deterministic-plus-semantic-evaluation.md)).
3. **Review**: per-profile workflow (shortlist, save, reject, ... applied, interviewing, offer) with append-only history.
4. **Prepare**: tailoring recommendations are shown as a proposal and stored only on approval; documents render to Markdown, HTML, DOCX and PDF with retained inputs ([ADR-008](../adr/ADR-008-human-in-the-loop-external-actions.md)).
5. **Track**: applications, contacts, follow-ups, interviews, a pipeline board and funnel metrics derived from workflow history.

## Health and observability

`/health/live` reports the process is serving. `/health/ready` also queries PostgreSQL and returns 503 when it is unreachable; external AI availability never affects readiness. Logs are structured JSON with a request id and secret redaction ([security](../security/privacy.md)).

## Further reading

[ADR index](../adr/README.md) · [profiles](profiles.md) · [evaluation](evaluation.md) · [API reference](../api/README.md) · guides: [adding a job source](../guides/write-a-job-source-adapter.md), [adding an LLM provider](../guides/write-an-llm-provider.md), [Podman](../guides/podman.md), [Docker Desktop](../guides/docker-desktop.md)
