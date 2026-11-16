# API reference

The API is FastAPI; the OpenAPI document is generated from the code.

| What | Where (default `http://localhost:8000`) |
|---|---|
| Interactive docs | `/docs` |
| OpenAPI JSON | `/openapi.json` |
| Every endpoint, by area | [endpoints.md](endpoints.md) (generated; a test keeps it current) |
| Liveness / readiness | `/health/live`, `/health/ready` |

## Conventions

- **Versioning**: everything product-related is under `/api/v1`. Health checks are unversioned.
- **Profile scoping**: data a person owns lives under `/api/v1/profiles/{profile_id}/...`. A record id belonging to another profile returns `404`, never `403` and never the record ([ADR-005](../adr/ADR-005-profile-scoped-domain-model.md)). Job lists, dashboards and workflow endpoints take the active profile as `profile_id`.
- **Errors**: JSON `{"detail": ...}`. `404` missing (or not yours), `409` conflict or a forbidden workflow transition (nothing is written), `422` validation (a list of `{loc, msg, type}`; submitted values are never echoed back), `502` an AI provider failed (nothing is persisted), `403` an action blocked by demo mode.
- **Pagination**: `GET /api/v1/jobs` takes `limit`/`offset` and returns the total in the `X-Total-Count` header (exposed through CORS).
- **Request ids**: send `X-Request-ID` (1-64 characters of `[A-Za-z0-9._-]`) or one is generated; it is returned in the response header and present on every log line.
- **Secrets**: no endpoint ever returns an API key or OAuth token; configuration endpoints only report whether one is set.
- **Human approval**: preparation (`/prepare`) and calendar change proposals are read-only; they are only stored/applied by an explicit approve call.

## A typical session

```sh
curl -s localhost:8000/api/v1/profiles                      # pick a profile id
curl -s -X POST localhost:8000/api/v1/jobs/import -H 'content-type: application/json' \
  -d '{"title":"Platform Engineer","company":"Acme","description_text":"Python, Kubernetes"}'
curl -s "localhost:8000/api/v1/jobs?profile_id=$P&sort=score"   # inbox for that profile
curl -s -X POST localhost:8000/api/v1/jobs/$J/shortlist -H 'content-type: application/json' -d "{\"profile_id\":\"$P\"}"
```

Regenerate the endpoint table after changing routes: `cd backend && uv run python -m careerflow.scripts.docs_api > ../docs/api/endpoints.md`.
