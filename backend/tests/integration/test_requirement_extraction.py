import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.jobs import get_extraction_service, get_session
from careerflow.api.profiles import get_session as get_profile_session
from careerflow.application.ai.client import AiClient
from careerflow.application.ai.requirements import RequirementExtractionService, quote_is_grounded
from careerflow.domain.ai.ports import AiTimeoutError
from careerflow.infrastructure.database.models import Base, JobModel, JobRequirementModel
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.main import create_app
from careerflow.seed import seed_session

LUMEN = "Lead our LLM application platform. Python, C#, Azure and distributed systems at scale."

AI_ANSWER = {
    "summary": "Platform lead for LLM applications.",
    "required_skills": [
        {"text": "Python", "source_quote": "Python, C#, Azure", "confidence": 0.9},
        {"text": "Kubernetes", "source_quote": "Kubernetes operator experience", "confidence": 0.95},
    ],
    "preferred_skills": [{"text": "Azure", "source_quote": "Azure", "confidence": 0.7}],
    "architecture_expectations": [{"text": "distributed systems", "source_quote": "distributed systems at scale"}],
    "leadership_expectations": [{"text": "lead platform", "source_quote": "Lead our LLM application platform"}],
    "inferred_seniority": "principal",
}


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_session(session)
    return engine


def lumen_id(session: Session) -> str:
    return session.scalars(select(JobModel.id).where(JobModel.company == "Lumen Robotics")).one()


def service(session: Session, provider: object) -> RequirementExtractionService:
    return RequirementExtractionService(session, AiClient(provider))  # type: ignore[arg-type]


def test_ai_extraction_persists_with_provenance(engine) -> None:  # type: ignore[no-untyped-def]
    provider = FixtureProvider("fx-9").script("extract_requirements", json.dumps(AI_ANSWER))
    with Session(engine) as session:
        outcome = service(session, provider).extract(lumen_id(session))
        assert outcome.mode == "ai"
        assert outcome.summary.startswith("Platform lead")
        rows = list(session.scalars(select(JobRequirementModel)))
    by_text = {r.normalized_text: r for r in rows}
    assert {r.extractor for r in rows} == {"ai"}
    assert {(r.provider, r.model_name, r.prompt_version) for r in rows} == {("fixture", "fx-9", "v1")}
    assert by_text["Python"].required_level == "REQUIRED" and by_text["Python"].category == "skill"
    assert by_text["Azure"].required_level == "PREFERRED"
    assert by_text["distributed systems"].category == "architecture"
    assert by_text["lead platform"].category == "leadership"
    assert by_text["principal"].type == "seniority"


def test_quote_not_in_description_gets_low_confidence(engine) -> None:  # type: ignore[no-untyped-def]
    provider = FixtureProvider().script("extract_requirements", json.dumps(AI_ANSWER))
    with Session(engine) as session:
        service(session, provider).extract(lumen_id(session))
        rows = {r.normalized_text: r for r in session.scalars(select(JobRequirementModel))}
    assert rows["Python"].confidence == 0.9  # quote found verbatim
    assert rows["Kubernetes"].confidence == 0.3  # hallucinated quote: capped, not trusted
    assert quote_is_grounded("PYTHON,  c# ", LUMEN)
    assert not quote_is_grounded("", LUMEN)


def test_disabled_ai_falls_back_to_keywords_without_error(engine) -> None:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        outcome = service(session, DisabledProvider()).extract(lumen_id(session))
        assert outcome.mode == "keyword"
        assert "disabled" in (outcome.fallback_reason or "")
        rows = {(r.normalized_text, r.category): r for r in session.scalars(select(JobRequirementModel))}
    assert ("Python", "skill") in rows and ("Azure", "skill") in rows
    assert all(r.extractor == "keyword" and r.provider is None for r in rows.values())
    assert {r.normalized_text for r in rows.values() if r.type == "seniority"} == {"principal"}
    assert any(c == "architecture" for _, c in rows)  # "distributed system" cue


def test_keyword_fallback_separates_preferred_from_required(engine) -> None:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        job = JobModel(
            title="Senior Engineer",
            company="X",
            description_text="Requirements:\n- Python experience\n\nNice to have:\n- Tableau dashboards\n",
        )
        session.add(job)
        session.commit()
        RequirementExtractionService(session, None).extract(job.id)
        rows = {r.normalized_text: r.required_level for r in session.scalars(
            select(JobRequirementModel).where(JobRequirementModel.job_id == job.id)
        )}
    assert rows["Python"] == "REQUIRED"
    assert rows["Tableau"] == "PREFERRED"


def test_reextraction_replaces_extracted_rows_but_keeps_manual_ones(engine) -> None:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        job_id = lumen_id(session)
        session.add(
            JobRequirementModel(job_id=job_id, type="skill", normalized_text="Mine", source_text="manual")
        )
        session.commit()
        svc = service(session, DisabledProvider())
        svc.extract(job_id)
        first = len(svc.list_for_job(job_id))
        svc.extract(job_id)
        rows = svc.list_for_job(job_id)
    assert len(rows) == first  # no duplicates after a second run
    assert [r.normalized_text for r in rows if r.extractor is None] == ["Mine"]


def test_invalid_ai_output_persists_nothing(engine) -> None:  # type: ignore[no-untyped-def]
    from careerflow.domain.ai.ports import AiInvalidResponseError

    provider = FixtureProvider().script("extract_requirements", "garbage", '{"required_skills": "nope"}')
    with Session(engine) as session:
        with pytest.raises(AiInvalidResponseError):
            service(session, provider).extract(lumen_id(session))
        assert list(session.scalars(select(JobRequirementModel))) == []


@pytest.fixture
def api(engine) -> Generator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app()

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_profile_session] = session_override
    yield TestClient(app)


def test_api_fallback_when_ai_disabled(api: TestClient) -> None:
    job = api.get("/api/v1/jobs", params={"profile_id": api.get("/api/v1/profiles").json()[0]["id"]}).json()[0]
    # default settings: AI disabled -> keyword mode, still 200
    response = api.post(f"/api/v1/jobs/{job['id']}/extract-requirements")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "keyword" and body["requirements"]
    listed = api.get(f"/api/v1/jobs/{job['id']}/requirements").json()
    assert len(listed) == len(body["requirements"])
    assert all(r["extractor"] == "keyword" for r in listed)
    assert api.post("/api/v1/jobs/nope/extract-requirements").status_code == 404


def test_api_returns_502_for_invalid_ai_and_persists_nothing(api: TestClient, engine) -> None:  # type: ignore[no-untyped-def]
    provider = FixtureProvider().script("extract_requirements", "bad", "worse")

    def override() -> Generator[RequirementExtractionService]:
        with Session(engine) as session:
            yield RequirementExtractionService(session, AiClient(provider))

    api.app.dependency_overrides[get_extraction_service] = override  # type: ignore[attr-defined]
    with Session(engine) as session:
        job_id = lumen_id(session)
    response = api.post(f"/api/v1/jobs/{job_id}/extract-requirements")
    assert response.status_code == 502
    assert api.get(f"/api/v1/jobs/{job_id}/requirements").json() == []

    timeout = FixtureProvider().script("extract_requirements", AiTimeoutError("slow"))
    api.app.dependency_overrides[get_extraction_service] = lambda: RequirementExtractionService(  # type: ignore[attr-defined]
        Session(engine), AiClient(timeout, sleep=lambda _s: None)
    )
    assert api.post(f"/api/v1/jobs/{job_id}/extract-requirements").status_code == 502
