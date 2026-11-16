"""Adapter cases for the shared contract suite.

To put a new adapter under contract, add an ``AdapterCase`` to ``CASES``. Each case builds
the adapter for a scenario ("ok", "empty", "malformed") and, for network adapters, for a
transport scenario (see ``NETWORK_MODES``) using ``FakeHttp``, so no test touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from careerflow.domain.sources.ports import JobSourceAdapter
from careerflow.infrastructure.jobsources.feeds import GenericJsonJobAdapter, RssJobAdapter
from careerflow.infrastructure.jobsources.greenhouse import GreenhouseJobAdapter
from careerflow.infrastructure.jobsources.http import HttpResponse
from careerflow.infrastructure.jobsources.simple import FixtureJobAdapter, ManualJobAdapter

SECRET = "sk-test-SECRET-1234567890"
NETWORK_MODES = ("http_500", "http_429", "http_404", "timeout")


class FakeHttp:
    """Offline HttpClient: maps URL substrings to canned responses or exceptions."""

    def __init__(self, routes: dict[str, HttpResponse | Exception] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, dict[str, str], float]] = []
        self.default: HttpResponse | Exception = HttpResponse(404, "not found")

    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0) -> HttpResponse:
        self.calls.append((url, dict(headers or {}), timeout))
        for fragment, outcome in self.routes.items():
            if fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        if isinstance(self.default, Exception):
            raise self.default
        return self.default


@dataclass
class AdapterCase:
    id: str
    build: Callable[[str, FakeHttp], JobSourceAdapter]  # (mode, http) -> adapter
    network: bool = False
    expected_name: str = ""
    extra: dict[str, str] = field(default_factory=dict)


GOOD = {
    "title": "Platform Engineer",
    "company": "Contoso Labs",
    "description_text": "Build internal platforms with Python.",
    "location_text": "Remote, United States",
    "remote_type": "REMOTE",
    "salary_min": 150000,
    "salary_max": 190000,
    "salary_currency": "USD",
    "salary_period": "YEAR",
    "posted_at": "2026-10-01T09:00:00Z",
    "external_id": "contoso-1",
}


def _manual(mode: str, http: FakeHttp) -> JobSourceAdapter:
    job = {"empty": {}, "malformed": {"title": "No company or description"}}.get(mode, GOOD)
    if mode == "empty":  # a manual source always holds exactly one job; an empty one is invalid
        job = {}
    return ManualJobAdapter({"job": job})


def _fixture(mode: str, http: FakeHttp) -> JobSourceAdapter:
    items = {
        "ok": [GOOD, {**GOOD, "external_id": "contoso-2", "title": "Data Engineer"}],
        "empty": [],
        "malformed": [{"title": "Missing the rest", "external_id": "bad-1"}],
    }[mode]
    return FixtureJobAdapter({"items": items})


FIXTURES = Path(__file__).parent.parent / "fixtures" / "sources"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _routes(http: FakeHttp, body: str) -> None:
    if not http.routes:  # network-failure scenarios pre-install their own routes
        http.routes = {"": HttpResponse(200, body)}


def _rss(fixture: str) -> Callable[[str, FakeHttp], JobSourceAdapter]:
    def build(mode: str, http: FakeHttp) -> JobSourceAdapter:
        body = {
            "ok": fixture_text(fixture),
            "empty": '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>',
            "malformed": '<rss version="2.0"><channel><title>T</title><item><title>X at Y</title></item></channel></rss>',
        }[mode]
        _routes(http, body)
        return RssJobAdapter({"url": "https://careers.example.com/feed", "api_key": SECRET}, http)

    return build


JSON_CONFIG = {
    "url": "https://jobs.example.org/api/postings",
    "items_path": "data.postings",
    "external_id_path": "id",
    "field_map": {
        "title": "role",
        "description_text": "summary",
        "location_text": "where.city",
        "salary_min": "pay.low",
        "salary_max": "pay.high",
        "salary_currency": "pay.ccy",
        "canonical_url": "url",
        "posted_at": "published",
    },
    "static": {"company": "Example Org", "salary_period": "YEAR"},
}


def _json(mode: str, http: FakeHttp) -> JobSourceAdapter:
    body = {
        "ok": fixture_text("json_feed.json"),
        "empty": json.dumps({"data": {"postings": []}}),
        "malformed": json.dumps({"data": {"postings": [{"id": 1, "role": "No description"}]}}),
    }[mode]
    _routes(http, body)
    return GenericJsonJobAdapter({**JSON_CONFIG, "api_key": SECRET}, http)


def _greenhouse(mode: str, http: FakeHttp) -> JobSourceAdapter:
    body = {
        "ok": fixture_text("greenhouse.json"),
        "empty": json.dumps({"jobs": []}),
        "malformed": json.dumps({"jobs": [{"id": 1, "title": "No content", "location": {"name": "X"}}]}),
    }[mode]
    _routes(http, body)
    return GreenhouseJobAdapter({"board_token": "acmerobotics", "company": "Acme Robotics"}, http)


CASES: list[AdapterCase] = [
    AdapterCase("manual", _manual, expected_name="manual"),
    AdapterCase("fixture", _fixture, expected_name="fixture"),
    AdapterCase("rss", _rss("rss.xml"), network=True, expected_name="rss"),
    AdapterCase("atom", _rss("atom.xml"), network=True, expected_name="rss"),
    AdapterCase("generic_json", _json, network=True, expected_name="generic_json"),
    AdapterCase("greenhouse", _greenhouse, network=True, expected_name="greenhouse"),
]
