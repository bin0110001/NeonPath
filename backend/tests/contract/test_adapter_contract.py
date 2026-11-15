"""Shared contract every JobSourceAdapter must pass (plan section 27). Runs offline."""

from __future__ import annotations

import pytest

from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    JobSourceAdapter,
    NormalizedJob,
    SourceCapabilities,
    SourceError,
    SourceFetchError,
    SourceJobReference,
    SourceParseError,
    SourceRateLimitedError,
)
from careerflow.infrastructure.jobsources.http import HttpResponse
from tests.contract.cases import CASES, NETWORK_MODES, SECRET, AdapterCase, FakeHttp

ALL = pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
NETWORK = pytest.mark.parametrize("case", [c for c in CASES if c.network], ids=lambda c: c.id)


def run_all(adapter: JobSourceAdapter) -> list[NormalizedJob]:
    return [
        adapter.normalize(adapter.fetch(ref)) for ref in adapter.discover(DiscoveryRequest())
    ]


@ALL
def test_initializes_with_declared_metadata(case: AdapterCase) -> None:
    adapter = case.build("ok", FakeHttp())
    assert adapter.name == case.expected_name
    caps = adapter.capabilities
    assert isinstance(caps, SourceCapabilities) and caps.access_method
    if case.network:
        assert caps.rate_limit_per_minute and caps.rate_limit_per_minute > 0
        assert caps.terms_url, "network adapters must document the source's terms"


@ALL
def test_discover_returns_canonical_references(case: AdapterCase) -> None:
    adapter = case.build("ok", FakeHttp())
    refs = list(adapter.discover(DiscoveryRequest()))
    assert refs
    assert all(isinstance(r, SourceJobReference) and r.external_id for r in refs)
    assert len({r.external_id for r in refs}) == len(refs)


@ALL
def test_discover_honors_limit(case: AdapterCase) -> None:
    adapter = case.build("ok", FakeHttp())
    assert len(list(adapter.discover(DiscoveryRequest(limit=1)))) <= 1


@ALL
def test_normalized_jobs_have_the_canonical_fields(case: AdapterCase) -> None:
    for job in run_all(case.build("ok", FakeHttp())):
        assert job.title.strip() and job.company.strip() and job.description_text.strip()
        assert job.external_id
        assert job.salary_min is None or isinstance(job.salary_min, float)
        assert job.posted_at is None or job.posted_at.tzinfo is not None


@ALL
def test_fetch_keeps_a_raw_payload_snapshot(case: AdapterCase) -> None:
    adapter = case.build("ok", FakeHttp())
    ref = next(iter(adapter.discover(DiscoveryRequest())))
    document = adapter.fetch(ref)
    assert isinstance(document.raw_payload, dict) and document.raw_payload
    assert document.reference == ref


@ALL
def test_empty_result_is_handled(case: AdapterCase) -> None:
    try:
        adapter = case.build("empty", FakeHttp())
        refs = list(adapter.discover(DiscoveryRequest()))
    except SourceError:
        return  # rejecting an empty source with a SourceError is acceptable
    assert refs == [] or all(isinstance(r, SourceJobReference) for r in refs)


@ALL
def test_malformed_data_raises_parse_errors_only(case: AdapterCase) -> None:
    with pytest.raises(SourceParseError):
        run_all(case.build("malformed", FakeHttp()))


@NETWORK
@pytest.mark.parametrize("mode", NETWORK_MODES)
def test_transport_failures_are_normalised(case: AdapterCase, mode: str) -> None:
    http = FakeHttp()
    outcome: HttpResponse | Exception = {
        "http_500": HttpResponse(500, "boom"),
        "http_429": HttpResponse(429, "slow down", {"Retry-After": "7"}),
        "http_404": HttpResponse(404, "gone"),
        "timeout": SourceFetchError("timed out"),
    }[mode]
    http.default = outcome
    http.routes = {"": outcome}
    with pytest.raises(SourceFetchError) as info:
        run_all(case.build("ok", http))
    error = info.value
    if mode == "http_429":
        assert isinstance(error, SourceRateLimitedError) and error.retry_after_seconds == 7
    if mode == "http_404":
        assert error.retryable is False
    if mode in ("http_500", "timeout"):
        assert error.retryable is True


@NETWORK
def test_requests_carry_a_timeout_and_never_leak_credentials(case: AdapterCase) -> None:
    http = FakeHttp()
    adapter = case.build("ok", http)
    run_all(adapter)
    assert http.calls
    assert all(timeout > 0 for _, _, timeout in http.calls)
    assert all(SECRET not in url for url, _, _ in http.calls)  # credentials go in headers, never URLs


@NETWORK
def test_errors_do_not_leak_credentials(case: AdapterCase) -> None:
    http = FakeHttp()
    http.default = HttpResponse(500, f"echo {SECRET}")
    http.routes = {"": http.default}
    with pytest.raises(SourceFetchError) as info:
        run_all(case.build("ok", http))
    assert SECRET not in str(info.value)
