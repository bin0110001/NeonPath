---
name: neonpath-testing
description: How to test and validate changes in NeonPath/CareerFlow. Use when implementing, fixing or reviewing code here.
---
# NeonPath Testing and Validation

Project-owned skill.

## Commands

Prefer the factory wrappers; they print compact JSON and keep logs in `.factory/artifacts/` (read a log only when a failure needs it):

- `pwsh scripts/factory/test-changed.ps1` - tests for what changed vs `main` (targeted).
- `pwsh scripts/factory/test-full.ps1` - full backend + frontend suites.
- `pwsh scripts/factory/verify.ps1` - what CI requires: ruff, mypy, pytest, eslint, `tsc` + vite build, vitest.

Underlying commands (run from the named directory):

- `backend/`: `uv sync --group dev`, `uv run pytest`, `uv run ruff check .`, `uv run mypy src` (strict).
- `frontend/`: `npm ci`, `npm run test`, `npm run lint`, `npm run build`.
- Compose smoke (CI only unless you changed compose/Containerfiles): `docker compose up -d --build`, then `/health/ready` on :8000 and :5173.

## Conventions

- Backend tests: `backend/tests/unit/` (pure/service logic) and `backend/tests/integration/`. Integration tests use in-memory SQLite (`create_engine("sqlite://")`) and need no running services.
- Every new service behaviour gets a unit test; anything touching profile scoping gets an isolation test like `test_profile_isolation.py`.
- Frontend tests: Vitest + Testing Library in `frontend/tests/`, jsdom environment, setup in `tests/setup.ts`.
- Test with fictional data only.
- Backend lint is ruff (rules E, F, I, UP, B; line length 100); types are mypy strict on `src/careerflow`.
- A change is not done until `verify.ps1` reports `"status": "passed"`.

## Known pitfalls

- `uv` and `npm` must be on PATH; the wrappers install dependencies on first run if `.venv` / `node_modules` are missing.
- Do not paste whole logs into issue comments or prompts; quote the failing test and the artifact path.
