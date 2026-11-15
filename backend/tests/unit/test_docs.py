"""Keeps the documentation honest: links resolve, ADRs are complete, the API table is current."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from careerflow.main import create_app
from careerflow.scripts.docs_api import render_endpoint_table

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
MARKDOWN = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", *sorted(DOCS.rglob("*.md"))]
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(path: Path) -> None:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#", 1)[0]
        assert (path.parent / file_part).resolve().exists(), f"{path.name}: broken link {target}"


ADRS = sorted(p for p in (DOCS / "adr").glob("ADR-*.md"))
SECTIONS = ("## Status", "## Context", "## Decision", "## Alternatives considered", "## Consequences")


@pytest.mark.parametrize("path", ADRS, ids=lambda p: p.stem)
def test_every_adr_has_the_five_sections(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for heading in SECTIONS:
        assert heading in text, f"{path.name} is missing {heading}"
    assert re.search(r"## Status\s+(Accepted|Proposed|Superseded)", text), path.name


def test_adr_index_lists_every_adr_and_the_plans_twelve_exist() -> None:
    index = (DOCS / "adr" / "README.md").read_text(encoding="utf-8")
    for path in ADRS:
        assert path.name in index, f"{path.name} is not in the ADR index"
    numbers = {int(p.name.split("-")[1]) for p in ADRS}
    assert set(range(1, 13)) <= numbers  # ADR-001..012 from section 39 of the plan


def test_endpoint_reference_is_current() -> None:
    expected = render_endpoint_table(create_app().openapi())
    actual = (DOCS / "api" / "endpoints.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, "run: cd backend && uv run python -m careerflow.scripts.docs_api > ../docs/api/endpoints.md"


def test_documented_conventions_exist_in_the_api() -> None:
    spec = create_app().openapi()["paths"]
    for path in ("/health/live", "/health/ready", "/api/v1/profiles", "/api/v1/jobs", "/api/v1/jobs/import", "/api/v1/sources", "/api/v1/ai/test"):
        assert path in spec, path
    api_readme = (DOCS / "api" / "README.md").read_text(encoding="utf-8")
    for needle in ("/docs", "/openapi.json", "X-Total-Count", "X-Request-ID"):
        assert needle in api_readme


def test_guides_reference_real_code() -> None:
    guide = (DOCS / "guides" / "write-a-job-source-adapter.md").read_text(encoding="utf-8")
    for name in ("SourceCapabilities", "SourceParseError", "get_checked", "normalize_mapping", "ADAPTERS"):
        assert name in guide
    import careerflow.infrastructure.jobsources.common as common
    import careerflow.infrastructure.jobsources.http as http
    import careerflow.infrastructure.jobsources.registry as registry

    assert hasattr(common, "normalize_mapping") and hasattr(http, "get_checked") and hasattr(registry, "ADAPTERS")
    provider = (DOCS / "guides" / "write-an-llm-provider.md").read_text(encoding="utf-8")
    import careerflow.infrastructure.llm.factory as factory
    import careerflow.infrastructure.llm.http_providers as providers

    for name in ("PROVIDERS", "PROVIDER_INFO"):
        assert name in provider and hasattr(factory, name)
    for name in ("HttpxLlmClient", "LlmHttp"):
        assert name in provider and hasattr(providers, name)
