"""Job source adapter contract (plan section 9).

Adapters turn an outside source into canonical jobs. They are read-only, declare their
compliance/operational metadata, and raise only ``SourceError`` subclasses. The canonical
job has no source-specific fields: anything source-specific lives in ``raw_payload``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class SourceError(Exception):
    """Base class for adapter failures. Messages must never contain credentials."""


class SourceConfigError(SourceError):
    """The source is misconfigured (missing/invalid settings). Not retryable."""


class SourceFetchError(SourceError):
    """Network or upstream failure. ``retryable`` tells the ingestion layer to back off."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class SourceRateLimitedError(SourceFetchError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message, retryable=True)
        self.retry_after_seconds = retry_after_seconds


class SourceParseError(SourceError):
    """The upstream data was malformed or missing required fields."""


@dataclass(frozen=True)
class SourceCapabilities:
    """Compliance and operational metadata every adapter must declare."""

    access_method: str  # e.g. "manual", "fixture", "rss", "public_api"
    can_discover: bool = True
    requires_credentials: bool = False
    rate_limit_per_minute: int | None = None  # None = no network, no limit needed
    terms_url: str | None = None
    retention_days: int | None = None  # how long raw payloads may be kept; None = indefinitely
    redistribution_allowed: bool = False


@dataclass(frozen=True)
class DiscoveryRequest:
    query: str | None = None
    location: str | None = None
    limit: int = 100


@dataclass(frozen=True)
class SourceJobReference:
    external_id: str
    url: str | None = None
    hint: dict[str, Any] = field(default_factory=dict)  # adapter-private data for fetch()


@dataclass(frozen=True)
class SourceJobDocument:
    reference: SourceJobReference
    raw_payload: dict[str, Any]


@dataclass
class NormalizedJob:
    """The canonical job fields an adapter can supply."""

    title: str
    company: str
    description_text: str
    external_id: str
    source_url: str | None = None
    canonical_url: str | None = None
    company_domain: str | None = None
    description_html: str | None = None
    location_text: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    industry: str | None = None
    requirements: list[dict[str, Any]] = field(default_factory=list)


class JobSourceAdapter(Protocol):
    name: str
    capabilities: SourceCapabilities

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]: ...

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument: ...

    def normalize(self, document: SourceJobDocument) -> NormalizedJob: ...
