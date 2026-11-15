# Running CareerFlow with Podman

CareerFlow's Compose file avoids anything engine-specific (no engine socket, no privileged containers, no host networking, no hard-coded UIDs), so rootless Podman works.

## Requirements

- Podman 4.7+ with `podman compose` (it delegates to `podman-compose` or `docker-compose`; either works). On Windows and macOS start the machine first: `podman machine init && podman machine start`.

## Start

```sh
git clone <repository-url> careerflow && cd careerflow
cp .env.example .env
podman compose up -d --build
```

Open `http://localhost:5173`. The first start builds the images, applies migrations, seeds two fictional profiles and starts the API (`:8000`), worker and web. Check health:

```sh
podman compose ps                       # api, worker, web, db should become healthy
curl http://localhost:8000/health/ready
```

Stop with `podman compose down`; add `-v` to also delete the database volume (this erases your data).

## Notes and troubleshooting

- **Rootless ports**: ports below 1024 need extra configuration; CareerFlow uses 5173 and 8000 (`FRONTEND_PORT`, `BACKEND_PORT` in `.env`).
- **SELinux (Fedora, RHEL, Bazzite)**: the base file uses named volumes only, so no `:Z` labels are needed. If you add bind mounts (for example in `compose.dev.yaml`) append `:Z` to them.
- **Windows build error about `.pytest_cache` or other access denied files**: delete the offending cache folder (`backend/.pytest_cache`, `frontend/node_modules/.vite`) or build the images directly (`podman build -f backend/Containerfile -t careerflow-api backend`) and run `podman compose up -d --no-build`.
- **Images are named by Compose** (`careerflow-api`, `careerflow-worker`, `careerflow-web`); the worker reuses the API codebase with a different command.
- **Reset the demo**: `podman compose exec api uv run python -m careerflow.demo reset` (demo mode only).
- Run the end-to-end tests against the stack: `cd frontend && npm ci && npx playwright install chromium && npm run e2e`.

## Differences from Docker

None are required. CI runs both: a Docker Compose smoke test with the end-to-end suite and a rootless Podman smoke test.
