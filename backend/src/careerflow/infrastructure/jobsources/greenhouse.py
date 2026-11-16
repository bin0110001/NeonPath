"""Greenhouse job board adapter (public, read-only Job Board API).

Docs/terms: https://developers.greenhouse.io/job-board.html (no credentials needed for
published boards). Greenhouse-specific fields never reach the canonical Job; they stay in
``JobSourceRecord.raw_payload``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    NormalizedJob,
    SourceCapabilities,
    SourceConfigError,
    SourceJobDocument,
    SourceJobReference,
    SourceParseError,
)
from careerflow.infrastructure.jobsources.common import dig, html_to_text, normalize_mapping
from careerflow.infrastructure.jobsources.http import HttpClient, get_checked

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
TERMS = "https://developers.greenhouse.io/job-board.html"
_BOARD = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class GreenhouseJobAdapter:
    name = "greenhouse"

    def __init__(self, config: dict[str, Any], http: HttpClient) -> None:
        board = config.get("board_token")
        if not isinstance(board, str) or not _BOARD.match(board):
            raise SourceConfigError("'board_token' is required (letters, digits, - and _)")
        self.board = board
        self.company = str(config.get("company") or board.replace("-", " ").replace("_", " ").title())
        self.timeout = float(config.get("timeout_seconds", 15))
        self.http = http
        self.capabilities = SourceCapabilities(
            access_method="public_api",
            requires_credentials=False,
            rate_limit_per_minute=int(config.get("rate_limit_per_minute", 30)),
            terms_url=TERMS,
            retention_days=config.get("retention_days"),
            redistribution_allowed=False,
        )

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]:
        url = API.format(board=quote(self.board, safe=""))
        text = get_checked(self.http, url, timeout=self.timeout).text
        try:
            body = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceParseError("Greenhouse response is not valid JSON") from error
        jobs = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(jobs, list):
            raise SourceParseError("Greenhouse response has no 'jobs' list")
        query = (request.query or "").lower()
        count = 0
        for job in jobs:
            if not isinstance(job, dict) or job.get("id") is None:
                raise SourceParseError("Greenhouse job without an id")
            if query and query not in str(job.get("title", "")).lower():
                continue
            if count >= request.limit:
                return
            count += 1
            yield SourceJobReference(str(job["id"]), job.get("absolute_url"), hint=job)

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument:
        # `content=true` already returned the full posting.
        return SourceJobDocument(reference, dict(reference.hint))

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        job = document.raw_payload
        location = dig(job, "location.name")
        content = job.get("content") or ""
        mapped: dict[str, Any] = {
            "title": job.get("title"),
            "company": self.company,
            "description_text": html_to_text(content),
            "description_html": content or None,
            "location_text": location,
            "remote_type": "REMOTE" if isinstance(location, str) and "remote" in location.lower() else None,
            "canonical_url": job.get("absolute_url"),
            "posted_at": job.get("first_published") or job.get("updated_at"),
        }
        return normalize_mapping(mapped, document.reference.external_id, job.get("absolute_url"))
