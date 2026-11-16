"""Stable identity of a posting, used for exact duplicate detection."""

from __future__ import annotations

import hashlib
import re

_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|gmbh|corp|corporation|co|company|plc)\b\.?")


def _norm(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
    return " ".join(text.split())


def normalize_company(company: str | None) -> str:
    return " ".join(_COMPANY_SUFFIX.sub(" ", _norm(company)).split())


def normalize_title(title: str | None) -> str:
    return _norm(title)


def normalize_location(location: str | None) -> str:
    text = _norm(location)
    for noise in ("remote", "hybrid", "onsite", "on site"):
        text = text.replace(noise, " ")
    return " ".join(text.split())


def job_fingerprint(company: str | None, title: str | None, location: str | None) -> str:
    """SHA-256 over normalised company + title + location (work-arrangement words ignored)."""
    key = "\x1f".join([normalize_company(company), normalize_title(title), normalize_location(location)])
    return hashlib.sha256(key.encode()).hexdigest()
