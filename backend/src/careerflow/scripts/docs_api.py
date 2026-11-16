"""Render the endpoint reference from the live OpenAPI document.

    uv run python -m careerflow.scripts.docs_api > ../docs/api/endpoints.md

A test regenerates this table and fails if ``docs/api/endpoints.md`` is out of date, so the
documentation cannot silently drift from the code.
"""

from __future__ import annotations

from typing import Any

from careerflow.main import create_app

METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
HEADER = """# API endpoints

Generated from the OpenAPI document by `python -m careerflow.scripts.docs_api`; do not edit by
hand (a test fails if it is stale). Interactive docs: `/docs`. Machine-readable: `/openapi.json`.
Every path below is relative to the API origin; profile-owned data lives under
`/api/v1/profiles/{profile_id}/...`.
"""


def _group(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if not parts or parts[0] == "health":
        return "health"
    if parts[:2] == ["api", "v1"] and len(parts) > 2:
        if parts[2] == "profiles" and len(parts) > 4:
            return f"profiles/{{id}}/{parts[4]}"
        return parts[2]
    return parts[0]


def endpoint_rows(openapi: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows = []
    for path, operations in openapi["paths"].items():
        for method, operation in operations.items():
            if method.upper() not in METHOD_ORDER:
                continue
            summary = (operation.get("summary") or "").strip()
            rows.append((path, method.upper(), summary))
    return sorted(rows, key=lambda r: (_group(r[0]), r[0], METHOD_ORDER[r[1]]))


def render_endpoint_table(openapi: dict[str, Any]) -> str:
    lines = [HEADER]
    current = ""
    for path, method, summary in endpoint_rows(openapi):
        group = _group(path)
        if group != current:
            current = group
            lines += ["", f"## {group}", "", "| Method | Path | Summary |", "|---|---|---|"]
        lines.append(f"| {method} | `{path}` | {summary} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    print(render_endpoint_table(create_app().openapi()), end="")


if __name__ == "__main__":
    main()
