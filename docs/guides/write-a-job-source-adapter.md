# How to write a job source adapter

An adapter turns an outside source into canonical jobs. You write one small class and register it; evaluation, workflow, scheduling, rate limiting, retries, run history and health reporting come from the framework ([ADR-006](../adr/ADR-006-source-adapter-architecture.md)).

**Ground rules.** Adapters are read-only. Only integrate sources whose terms allow it (declare the terms URL). No CAPTCHA bypass, no scraping of sites that forbid it. Never put credentials in the database or in URLs.

## 1. The contract

`backend/src/careerflow/domain/sources/ports.py`:

```python
class JobSourceAdapter(Protocol):
    name: str
    capabilities: SourceCapabilities          # declared compliance/operational metadata

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]: ...
    def fetch(self, reference: SourceJobReference) -> SourceJobDocument: ...
    def normalize(self, document: SourceJobDocument) -> NormalizedJob: ...
```

- `discover` lists what exists (honour `request.limit`; `request.query` is optional).
- `fetch` returns the raw record as a dict. It is stored verbatim as the source record's `raw_payload`. If `discover` already returned the whole item, return it from `reference.hint` (no second request).
- `normalize` maps it to `NormalizedJob`: **only canonical fields**. Anything source-specific stays in the raw payload.
- Raise only `SourceError` subclasses: `SourceConfigError` (bad settings, not retried), `SourceFetchError(retryable=...)`, `SourceRateLimitedError`, `SourceParseError` (malformed data). Messages must never contain credentials.

## 2. Example: a minimal JSON board

```python
# backend/src/careerflow/infrastructure/jobsources/myboard.py
from careerflow.domain.sources.ports import (
    DiscoveryRequest, NormalizedJob, SourceCapabilities, SourceConfigError,
    SourceJobDocument, SourceJobReference,
)
from careerflow.infrastructure.jobsources.common import normalize_mapping
from careerflow.infrastructure.jobsources.http import HttpClient, get_checked
import json


class MyBoardAdapter:
    name = "myboard"

    def __init__(self, config: dict, http: HttpClient) -> None:
        if not str(config.get("board", "")).isidentifier():
            raise SourceConfigError("'board' is required")
        self.board, self.http = config["board"], http
        self.capabilities = SourceCapabilities(
            access_method="public_api",
            rate_limit_per_minute=30,                 # the framework enforces this spacing
            terms_url="https://example.com/api-terms",
        )

    def discover(self, request: DiscoveryRequest):
        response = get_checked(self.http, f"https://example.com/api/{self.board}/jobs", timeout=15)
        for item in json.loads(response.text)["jobs"][: request.limit]:
            yield SourceJobReference(str(item["id"]), item.get("url"), hint=item)

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument:
        return SourceJobDocument(reference, dict(reference.hint))

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        item = document.raw_payload
        return normalize_mapping(
            {"title": item.get("title"), "company": "Example", "description_text": item.get("text"),
             "location_text": item.get("location"), "canonical_url": item.get("url")},
            document.reference.external_id,
        )
```

`get_checked` already turns HTTP 429 into `SourceRateLimitedError` (with `Retry-After`), 5xx into a retryable `SourceFetchError` and 4xx into a non-retryable one. `normalize_mapping` validates required fields and raises `SourceParseError` for you. Credentials: accept `api_key_env` in config; the registry resolves it from the environment into `config["api_key"]` at runtime, and you send it in a header.

## 3. Register it

In `infrastructure/jobsources/registry.py`:

```python
ADAPTERS["myboard"] = lambda config, http: MyBoardAdapter(config, http)
```

Nothing else changes. A user can now create a source (`POST /api/v1/sources` with `{"name": "...", "adapter": "myboard", "config": {"board": "acme"}}`), run it (`POST /api/v1/sources/{id}/run`) or attach it to a scheduled search.

## 4. Put it under the shared contract

Add recorded responses to `backend/tests/fixtures/sources/` and a case to `backend/tests/contract/cases.py`:

```python
AdapterCase("myboard", _myboard, network=True, expected_name="myboard"),
```

The contract suite then checks, with no network: metadata is declared (a rate limit and terms URL for network adapters), references are unique, `limit` is honoured, normalised jobs have the canonical fields, an empty source is fine, malformed data raises `SourceParseError`, HTTP 429/500/404 and timeouts become the right `SourceError`, requests carry a timeout and credentials never appear in URLs or errors. Add adapter-specific mapping tests as in `tests/unit/test_adapter_mapping.py`. Run `uv run pytest tests/contract`.
