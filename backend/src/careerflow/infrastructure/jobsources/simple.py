"""Adapters that need no network: pasted/manual jobs and fixture files."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    NormalizedJob,
    SourceCapabilities,
    SourceConfigError,
    SourceJobDocument,
    SourceJobReference,
    SourceParseError,
)
from careerflow.infrastructure.jobsources.common import normalize_mapping, stable_id


class _InMemoryAdapter:
    """Base for adapters whose records are already in memory (``self._records``)."""

    name = "memory"
    capabilities = SourceCapabilities(access_method="memory", rate_limit_per_minute=None)

    def __init__(self) -> None:
        self._records: dict[str, Any] = {}

    def _register(self, record: Any) -> None:
        title = record.get("title") if isinstance(record, dict) else None
        company = record.get("company") if isinstance(record, dict) else None
        external = record.get("external_id") if isinstance(record, dict) else None
        external_id = str(external or stable_id(title, company, str(len(self._records))))
        self._records[external_id] = record

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]:
        for count, (external_id, record) in enumerate(self._records.items()):
            if count >= request.limit:
                return
            url = record.get("canonical_url") if isinstance(record, dict) else None
            yield SourceJobReference(external_id=external_id, url=url)

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument:
        record = self._records[reference.external_id]
        return SourceJobDocument(reference, record if isinstance(record, dict) else {"value": record})

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        raw = document.raw_payload
        return normalize_mapping(raw, document.reference.external_id, document.reference.url)


class ManualJobAdapter(_InMemoryAdapter):
    """A single pasted job description with optional URL/title/company metadata."""

    name = "manual"
    capabilities = SourceCapabilities(access_method="manual", rate_limit_per_minute=None, retention_days=None)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        job = config.get("job")
        if not isinstance(job, dict):
            raise SourceConfigError("manual source needs a 'job' object")
        # every paste is a new posting: a random id keeps two pastes from being merged by id
        self._register({"external_id": uuid.uuid4().hex, **job})


class FixtureJobAdapter(_InMemoryAdapter):
    """Jobs from inline ``items`` or a JSON ``path`` (fictional demo data)."""

    name = "fixture"
    capabilities = SourceCapabilities(access_method="fixture", rate_limit_per_minute=None)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        items = config.get("items")
        if items is None and config.get("path"):
            try:
                items = json.loads(Path(str(config["path"])).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise SourceConfigError(f"cannot read fixture file: {type(error).__name__}") from error
        if items is None:
            raise SourceConfigError("fixture source needs 'items' or 'path'")
        if not isinstance(items, list):
            raise SourceParseError("fixture items must be a list")
        for item in items:
            self._register(item)
