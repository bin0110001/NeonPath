"""Static checks on the GitHub Actions workflows (they cannot be executed locally).

These guard the properties that matter: nothing is published unless PUBLISH_IMAGES is
enabled, tokens are minimally scoped, and every required pipeline stage is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    data["on"] = data.pop(True, data.get("on"))  # YAML parses a bare `on:` key as boolean True
    return data


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_every_workflow_parses_and_has_jobs(name: str) -> None:
    workflow = load(name)
    assert workflow["jobs"] and workflow["on"]
    for job in workflow["jobs"].values():
        assert job.get("steps") or job.get("uses")


def test_ci_has_every_required_check() -> None:
    jobs = load("ci.yml")["jobs"]
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert {"backend", "frontend", "compose", "migrations", "images", "podman"} <= set(jobs)
    for needle in ("pytest", "ruff check", "mypy", "alembic check", "npm run typecheck", "npm run e2e", "podman compose up"):
        assert needle in text, needle


def test_release_triggers_and_stages() -> None:
    workflow = load("release.yml")
    assert workflow["on"]["push"]["branches"] == ["main"] and workflow["on"]["push"]["tags"] == ["v*"]
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    for needle in ("docker/build-push-action", "trivy-action", "anchore/sbom-action", "gh release create", "--generate-notes"):
        assert needle in text, needle
    steps = {s.get("name", ""): s for s in workflow["jobs"]["images"]["steps"]}
    assert {"Build OCI image", "Vulnerability gate (CRITICAL fails the release)", "Generate SBOM (SPDX)"} <= set(steps)


def test_publishing_only_happens_when_configured() -> None:
    workflow = load("release.yml")
    steps = workflow["jobs"]["images"]["steps"]
    build = next(s for s in steps if s.get("name") == "Build OCI image")
    login = next(s for s in steps if "Log in" in s.get("name", ""))
    assert build["with"]["push"] == "${{ env.PUBLISH == 'true' }}"  # never an unconditional push
    assert login["if"] == "env.PUBLISH == 'true'"
    assert workflow["jobs"]["images"]["env"]["PUBLISH"] == "${{ vars.PUBLISH_IMAGES == 'true' }}"
    assert "push: true" not in (WORKFLOWS / "release.yml").read_text(encoding="utf-8")


def test_permissions_are_minimal_and_notes_only_for_tags() -> None:
    workflow = load("release.yml")
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["release-notes"]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert workflow["jobs"]["release-notes"]["permissions"] == {"contents": "write"}
    assert workflow["jobs"]["images"]["permissions"]["packages"] == "write"


def test_no_secrets_other_than_the_workflow_token_are_used() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        used = {
            part.split("}}")[0].strip()
            for part in path.read_text(encoding="utf-8").split("secrets.")[1:]
        }
        assert used <= {"GITHUB_TOKEN"}, (path.name, used)
