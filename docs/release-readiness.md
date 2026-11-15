# Release readiness (v1.0.0)

This is the honest state of the project against the v1.0.0 success criteria in the implementation plan (section 42). Everything marked *verified* was run locally; items under *needs a maintainer* cannot be done from a development machine.

## Verified

- Start from a clean clone with `podman compose up -d --build` (rootless Podman on Windows via the machine VM): migrations, fictional seed data, API, worker and web all become healthy; the end-to-end suite passes against it.
- Two fictional profiles score the same jobs differently, with reasons (`docs/guides/scoring.md`), and a manually pasted job can be imported, evaluated per profile, shortlisted, prepared and moved through the pipeline.
- Backend: pytest (including PostgreSQL-only concurrency tests for the task queue and scheduler), ruff, mypy strict, migration upgrade → downgrade → upgrade and the autogenerate drift check on a clean database.
- Frontend: vitest, eslint, tsc, production build, Playwright end-to-end flow.
- Renderers (Markdown, HTML, DOCX, PDF) work inside the backend image and reproduce byte-for-byte from retained inputs.
- Documentation: relative links, ADR structure and the generated API reference are checked by tests.

## Needs a maintainer before tagging v1.0.0

1. **Run CI on GitHub.** `ci.yml` (Docker smoke + E2E, rootless Podman smoke, image builds, migrations) and `release.yml` (OCI images, Trivy scan, SBOM, release notes) are written and statically validated but have not executed on GitHub Actions. Expect to adjust action versions or runner details on the first run; consider pinning actions by SHA.
2. **Verify integrations against live services**, with your own credentials: Gmail (read-only) and Google Calendar OAuth, and any hosted/local LLM you intend to support. They were tested only against recorded responses.
3. **Docker Desktop on Windows and Podman on Linux**: the same Compose file is used, but only Podman (Windows machine) was exercised by hand here.
4. **Screenshots or a short recording** of the demo for the README (section 29).
5. **Decide whether to publish images**: set the repository variable `PUBLISH_IMAGES=true` and check package visibility; until then releases build and scan but do not push.
6. **Review the known limitations** in [privacy and security](security/privacy.md) and the open items below.
7. Create the tag: `git tag v1.0.0 && git push origin v1.0.0` (this triggers the release workflow).

## Open items and known gaps

- Profile editor UI is minimal: the API supports every entity type, but the UI only edits a profile's basics (issue #10).
- Single-user, no login (`AUTH_MODE=local`); put a reverse proxy with authentication in front of any shared deployment.
- PDF uses Latin-1 fonts; keyword/skill matching is word-based; calendar/mail support is Google only.
- Prompts have only been exercised with the fixture provider; quality with real models is untested.
