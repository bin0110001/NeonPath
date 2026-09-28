# Contributing

Use small vertical slices and preserve the backend boundaries: domain code must not depend on FastAPI, ORM entities must not be API responses, and external providers belong behind adapters.

Before opening a change, run backend tests/lint/type checking and frontend tests/lint/build. Keep the base `compose.yaml` portable across Podman and Docker; do not add privileged containers or engine-socket mounts.

Use fictional or redacted data only in committed fixtures and documentation.
