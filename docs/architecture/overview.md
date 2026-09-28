# Architecture overview

CareerFlow is a monorepo containing a React web client and a Python API. PostgreSQL is the operational datastore. The base Compose file uses only the current Compose Specification, named volumes, and unprivileged services so it is portable between Docker Compose and Podman Compose.

```text
Browser → React web → FastAPI API → application services → domain
                                      ↓
                              infrastructure adapters → PostgreSQL
```

Phase 0 intentionally has no business entities. It establishes the extension points: `domain` contains business rules, `application` coordinates use cases, `infrastructure` owns database/external implementations, and `api` adapts HTTP. The API and future worker can share the backend image and codebase.

`/health/live` verifies that the process is serving. `/health/ready` additionally executes a database query and returns 503 if PostgreSQL is unavailable.
