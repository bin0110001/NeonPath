# ADR-006: Job source adapter architecture

## Status

Accepted

## Context

Jobs arrive from many places (pasted text, fixtures, feeds, public APIs, ATS boards). Evaluation and workflow code must not know where a job came from, and every source needs consistent politeness, retry and visibility.

## Decision

`domain/sources/ports.py` defines the `JobSourceAdapter` contract (`discover`, `fetch`, `normalize`), declared `SourceCapabilities` (access method, credentials, rate limit, terms URL, retention, redistribution) and a `SourceError` hierarchy. Adapters are read-only and produce a `NormalizedJob`: only canonical fields, never source-specific ones. Anything source-specific is stored in `JobSourceRecord.raw_payload`.

`application/sources/ingest.py` owns cross-cutting policy so adapters stay small: rate limiting from the declared limit, retry with exponential backoff (honouring `Retry-After`), per-item failure isolation, raw snapshot retention, run history (`source_runs`) and health state (`HEALTHY`, `DEGRADED`, `FAILING`). New adapters register a factory in `infrastructure/jobsources/registry.py`; nothing in evaluation or workflow changes. Configured sources live in `job_sources`; credentials are never stored, only the name of an environment variable (`api_key_env`). Adapters reach the network through an injectable `HttpClient`, so contract tests run offline against recorded fixtures.

Manual and fixture imports run on the same framework (`ManualJobAdapter`, `FixtureJobAdapter`). Adapters are synchronous for the same reason as the LLM port (ADR-007).

## Alternatives considered

Per-source code paths in the API (duplicated policy, impossible to test uniformly); a plugin loader (premature; a registry dict is enough for now); scraping-first design (rejected: terms and robustness).

## Consequences

Every adapter must pass the shared contract suite in `tests/contract`. Respecting a source's terms is the adapter author's responsibility and is documented through `terms_url`.
