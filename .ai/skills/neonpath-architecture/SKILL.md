---
name: neonpath-architecture
description: NeonPath/CareerFlow architecture rules and conventions. Use when planning, implementing or reviewing any change in this repository.
---
# NeonPath (CareerFlow) Architecture

Project-owned skill. Factory skills (`factory-plan`, `factory-implement`, `factory-review`, `factory-fix`) defer to it for repository specifics.

## Shape

Monorepo: React + TypeScript web client (`frontend/`), FastAPI API (`backend/`), PostgreSQL. Flow: browser -> React -> FastAPI -> application services -> domain; infrastructure adapters own PostgreSQL and external providers.

## Backend boundaries (blocking if violated)

- `domain/` holds business rules and must not import FastAPI, SQLAlchemy or pydantic-settings.
- `application/` coordinates use cases and may depend on domain and infrastructure abstractions.
- `infrastructure/` owns database and external-provider implementations. ORM entities are never returned as API responses; map to schemas in `api/schemas/`.
- `api/` only adapts HTTP: routing, request/response schemas, status codes.
- External providers (job boards, AI) sit behind adapters, never called from domain or API code directly.
- All career data is scoped by an explicit `profile_id`. No profile-specific values in code. Cross-profile references must be rejected in the application service (see `docs/architecture/profiles.md`).
- Schema changes need an Alembic migration in `backend/migrations/versions/`; do not edit applied migrations.

## Frontend

React + TypeScript (strict), feature folders under `frontend/src/features/`, routing with react-router. No `any` (ESLint enforces `no-explicit-any`), no unused variables.

## Repository rules

- Small vertical slices; avoid sweeping refactors.
- Keep base `compose.yaml` portable across Podman and Docker: no privileged containers, no engine-socket mounts, no engine-specific `version` field (ADR-010).
- Fictional or redacted data only in committed fixtures, seeds and docs (the demo profiles are Jordan Lee and Morgan Rivera).
- People stay in control of external actions: automation prepares and organises, it never submits applications or contacts third parties on its own.
- Record significant decisions as ADRs in `docs/adr/` and keep `docs/architecture/` current when behaviour changes.
- Never commit `.env`; only `.env.example`.

## Risk guidance for labels

- `risk:low`: docs, tests, small isolated UI or backend fixes.
- `risk:medium`: new features, refactors, new endpoints, persistence changes.
- `risk:high`: migrations that alter or drop data, anything touching secrets/auth, external-provider integrations that act on a user's behalf, compose/deployment changes.
