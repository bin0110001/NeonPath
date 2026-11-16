"""Shared helpers for adapters: canonical-field mapping and safe parsing."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from typing import Any

from careerflow.domain.sources.ports import NormalizedJob, SourceParseError

REQUIRED = ("title", "company", "description_text")
STRING_FIELDS = (
    "canonical_url", "company_domain", "description_html", "location_text", "remote_type",
    "employment_type", "salary_currency", "salary_period", "industry",
)  # fmt: skip
NUMBER_FIELDS = ("salary_min", "salary_max")
DATE_FIELDS = ("posted_at", "expires_at")


def stable_id(*parts: str | None) -> str:
    digest = hashlib.sha256("\x1f".join((p or "").strip().lower() for p in parts).encode()).hexdigest()
    return digest[:24]


_TAGS = re.compile(r"<[^>]+>")
_BLOCKS = re.compile(r"(?i)</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>")


def html_to_text(value: str) -> str:
    """Plain text from (possibly entity-escaped) HTML; keeps paragraph/list breaks."""
    text = html.unescape(value)
    if "<" in text:
        text = _TAGS.sub("", _BLOCKS.sub("\n", text))
    lines = [" ".join(line.split()) for line in html.unescape(text).splitlines()]
    return "\n".join(line for line in lines if line)


def dig(data: object, path: str) -> object:
    """Follow a dotted path (``a.b.0.c``) through dicts and lists; missing -> None."""
    current = data
    for part in filter(None, path.split(".")):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceParseError(f"invalid date: {value!r}") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_number(value: Any, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SourceParseError(f"{name} is not a number: {value!r}") from error


def normalize_mapping(
    raw: Any, external_id: str, source_url: str | None = None
) -> NormalizedJob:
    """Build a NormalizedJob from a dict that already uses canonical field names."""
    if not isinstance(raw, dict):
        raise SourceParseError("job record is not an object")
    for name in REQUIRED:
        value = raw.get(name)
        if not isinstance(value, str) or not value.strip():
            raise SourceParseError(f"missing required field: {name}")
    kwargs: dict[str, Any] = {name: raw[name].strip() for name in REQUIRED}
    for name in STRING_FIELDS:
        value = raw.get(name)
        kwargs[name] = str(value) if value not in (None, "") else None
    for name in NUMBER_FIELDS:
        kwargs[name] = to_number(raw.get(name), name)
    for name in DATE_FIELDS:
        kwargs[name] = parse_datetime(raw.get(name))
    requirements = raw.get("requirements") or []
    if not isinstance(requirements, list):
        raise SourceParseError("requirements must be a list")
    return NormalizedJob(
        external_id=external_id,
        source_url=source_url or raw.get("source_url") or raw.get("canonical_url"),
        requirements=[dict(r) for r in requirements if isinstance(r, dict)],
        **kwargs,
    )
