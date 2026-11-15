# Running CareerFlow with Docker Desktop

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine with the Compose plugin (Linux). Compose v2 (`docker compose`).

## Start

```sh
git clone <repository-url> careerflow && cd careerflow
cp .env.example .env          # on Windows PowerShell: Copy-Item .env.example .env
docker compose up -d --build
```

Open `http://localhost:5173`. Migrations and the fictional demo data are applied automatically on first start. Verify:

```sh
docker compose ps
curl http://localhost:8000/health/ready
```

`docker compose down` stops it; `docker compose down -v` also deletes the database volume.

## Notes

- **Windows**: use the WSL 2 backend. Clone into the WSL filesystem for much faster file access if you develop on it. Golden test files are forced to LF by `.gitattributes`, so tests pass with either line-ending setting.
- **Ports**: change `FRONTEND_PORT` / `BACKEND_PORT` in `.env` if 5173 or 8000 are taken.
- **Hot reload for development**: `docker compose -f compose.yaml -f compose.dev.yaml up --build`, then `npm run dev` in `frontend/`.
- **Reset the demo data**: `docker compose exec api uv run python -m careerflow.demo reset`.
- **Never** mount the Docker socket into a container and do not run with `--privileged`; CareerFlow does not need either.

See also [Podman](podman.md); the same Compose file serves both engines.
