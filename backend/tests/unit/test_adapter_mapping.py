from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.application.sources.ingest import IngestionService
from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    NormalizedJob,
    SourceConfigError,
    SourceParseError,
)
from careerflow.infrastructure.database.models import Base, JobModel, JobSourceRecordModel
from careerflow.infrastructure.jobsources.feeds import GenericJsonJobAdapter, RssJobAdapter
from careerflow.infrastructure.jobsources.greenhouse import GreenhouseJobAdapter
from careerflow.infrastructure.jobsources.http import HttpResponse
from careerflow.infrastructure.jobsources.registry import build_adapter
from tests.contract.cases import JSON_CONFIG, SECRET, FakeHttp, fixture_text


def jobs(adapter) -> list[NormalizedJob]:  # type: ignore[no-untyped-def]
    return [adapter.normalize(adapter.fetch(r)) for r in adapter.discover(DiscoveryRequest())]


def http_with(body: str) -> FakeHttp:
    http = FakeHttp()
    http.routes = {"": HttpResponse(200, body)}
    return http


def test_rss_maps_fields_and_cleans_html() -> None:
    first, second = jobs(RssJobAdapter({"url": "https://careers.example.com/feed"}, http_with(fixture_text("rss.xml"))))
    assert (first.title, first.company) == ("Platform Engineer", "Contoso Labs")  # "X at Y" title split
    assert first.external_id == "job-101"
    assert first.canonical_url == "https://careers.example.com/jobs/101"
    assert first.description_text == "Build internal platforms with Python.\nKubernetes\nCI/CD"
    assert first.description_html is not None and "<b>Python</b>" in first.description_html
    assert first.posted_at is not None and (first.posted_at.year, first.posted_at.month, first.posted_at.day) == (2026, 10, 1)
    assert (second.title, second.company) == ("Data Scientist", "Contoso Analytics")  # dc:creator
    assert second.description_text == "Forecasting and experimentation."  # content:encoded wins
    assert second.external_id == "https://careers.example.com/jobs/102"  # falls back to the link


def test_atom_feed_and_configured_company() -> None:
    (job,) = jobs(RssJobAdapter({"url": "https://f.example.com/atom", "company": "Fabrikam Inc"}, http_with(fixture_text("atom.xml"))))
    assert job.company == "Fabrikam Inc"  # explicit config beats parsing
    assert job.title == "Site Reliability Engineer at Fabrikam"
    assert job.external_id == "tag:fabrikam.example.com,2026:jobs/7"
    assert job.canonical_url == "https://fabrikam.example.com/jobs/7"
    assert job.description_text == "Keep services reliable."


def test_rss_rejects_xml_entity_attacks_and_garbage() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<rss><channel><title>&b;</title></channel></rss>"
    )
    for body in (bomb, "<rss><channel>", "not xml at all"):
        with pytest.raises(SourceParseError):
            list(RssJobAdapter({"url": "https://x.example.com/f"}, http_with(body)).discover(DiscoveryRequest()))


def test_generic_json_applies_field_mapping_and_static_values() -> None:
    first, second = jobs(GenericJsonJobAdapter(JSON_CONFIG, http_with(fixture_text("json_feed.json"))))
    assert (first.title, first.company, first.external_id) == ("Machine Learning Engineer", "Example Org", "9001")
    assert first.description_text == "Train and ship models."  # html -> text
    assert first.description_html == "<p>Train and ship <b>models</b>.</p>"
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (90000.0, 120000.0, "EUR", "YEAR")
    assert first.location_text == "Berlin, Germany" and second.location_text == "Remote"
    assert first.canonical_url == "https://jobs.example.org/9001"


def test_generic_json_config_and_shape_errors() -> None:
    with pytest.raises(SourceConfigError):
        GenericJsonJobAdapter({"url": "ftp://x/y", "field_map": {"title": "a", "description_text": "b"}}, FakeHttp())
    with pytest.raises(SourceConfigError, match="field_map"):
        GenericJsonJobAdapter({"url": "https://x.example.com", "field_map": {"title": "a"}}, FakeHttp())
    adapter = GenericJsonJobAdapter({**JSON_CONFIG, "items_path": "missing.path"}, http_with("{}"))
    with pytest.raises(SourceParseError, match="no list of jobs"):
        list(adapter.discover(DiscoveryRequest()))
    with pytest.raises(SourceParseError, match="valid JSON"):
        list(GenericJsonJobAdapter(JSON_CONFIG, http_with("<html>")).discover(DiscoveryRequest()))


def test_generic_json_sends_credentials_only_in_headers() -> None:
    http = http_with(fixture_text("json_feed.json"))
    adapter = GenericJsonJobAdapter({**JSON_CONFIG, "api_key": SECRET, "auth_header": "X-Api-Key", "auth_scheme": ""}, http)
    jobs(adapter)
    url, headers, timeout = http.calls[0]
    assert headers == {"X-Api-Key": SECRET} and SECRET not in url and timeout == 15
    assert adapter.capabilities.requires_credentials


def test_declared_capabilities_for_network_adapters() -> None:
    rss = RssJobAdapter({"url": "https://careers.example.com/feed"}, FakeHttp())
    assert rss.capabilities.terms_url == "https://careers.example.com/"
    assert rss.capabilities.rate_limit_per_minute == 6
    custom = RssJobAdapter({"url": "https://a.example.com/f", "terms_url": "https://a.example.com/tos", "rate_limit_per_minute": 2}, FakeHttp())
    assert (custom.capabilities.terms_url, custom.capabilities.rate_limit_per_minute) == ("https://a.example.com/tos", 2)
    gh = GreenhouseJobAdapter({"board_token": "acme"}, FakeHttp())
    assert gh.capabilities.access_method == "public_api" and not gh.capabilities.requires_credentials


def test_greenhouse_maps_to_canonical_fields_only() -> None:
    http = http_with(fixture_text("greenhouse.json"))
    adapter = GreenhouseJobAdapter({"board_token": "acme-robotics"}, http)
    first, second = jobs(adapter)
    assert http.calls[0][0] == "https://boards-api.greenhouse.io/v1/boards/acme-robotics/jobs?content=true"
    assert (first.title, first.company, first.external_id) == ("Staff Software Engineer, Platform", "Acme Robotics", "4012345")
    assert first.remote_type == "REMOTE" and second.remote_type is None
    assert first.description_text == "Lead the platform team.\nGo or Python\nDistributed systems"
    assert first.canonical_url == "https://boards.greenhouse.io/acmerobotics/jobs/4012345"
    assert first.posted_at is not None and first.posted_at.utcoffset() is not None
    assert not {"departments", "internal_job_id", "metadata"} & set(vars(first))  # nothing source-specific


def test_greenhouse_query_filter_limit_and_config_validation() -> None:
    adapter = GreenhouseJobAdapter({"board_token": "acme"}, http_with(fixture_text("greenhouse.json")))
    assert [r.external_id for r in adapter.discover(DiscoveryRequest(query="data"))] == ["4012346"]
    assert len(list(adapter.discover(DiscoveryRequest(limit=1)))) == 1
    for bad in ({}, {"board_token": "../etc/passwd"}, {"board_token": "a b"}, {"board_token": 5}):
        with pytest.raises(SourceConfigError):
            GreenhouseJobAdapter(bad, FakeHttp())


def test_greenhouse_source_specific_data_lives_only_in_the_raw_payload() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    adapter = GreenhouseJobAdapter({"board_token": "acme-robotics"}, http_with(fixture_text("greenhouse.json")))
    with Session(engine) as session:
        result = IngestionService(session, sleep=lambda _s: None).ingest(adapter)
        assert len(result.created) == 2 and result.failed == 0
        assert not {"departments", "internal_job_id", "metadata"} & {c.name for c in JobModel.__table__.columns}
        record = session.scalars(select(JobSourceRecordModel).where(JobSourceRecordModel.external_id == "4012345")).one()
        assert record.adapter == "greenhouse"
        assert record.raw_payload["departments"] == [{"id": 1, "name": "Engineering"}]
        assert record.raw_payload["internal_job_id"] == 777


def test_registry_builds_all_network_adapters_and_masks_nothing_it_should_not() -> None:
    assert build_adapter("greenhouse", {"board_token": "acme"}).name == "greenhouse"
    assert build_adapter("rss", {"url": "https://a.example.com/feed"}).name == "rss"
    with pytest.raises(SourceConfigError, match="unknown adapter"):
        build_adapter("linkedin", {})


@pytest.mark.skipif(not os.environ.get("GREENHOUSE_LIVE_BOARD"), reason="set GREENHOUSE_LIVE_BOARD to run against the real API")
def test_greenhouse_live_board() -> None:
    from careerflow.infrastructure.jobsources.http import HttpxClient

    adapter = GreenhouseJobAdapter({"board_token": os.environ["GREENHOUSE_LIVE_BOARD"]}, HttpxClient())
    found = list(adapter.discover(DiscoveryRequest(limit=3)))
    assert all(adapter.normalize(adapter.fetch(ref)).title for ref in found)
