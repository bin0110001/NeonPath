from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.tracking import get_session as tracking_session
from careerflow.application.ai.client import AiClient
from careerflow.application.applications.interview_service import InterviewPrepService
from careerflow.application.evaluations.semantic import collect_evidence
from careerflow.domain.ai.ports import AiTimeoutError
from careerflow.domain.applications.interview_prep import prepare
from careerflow.domain.applications.tailoring import AchievementFact, JobFacts, SkillFact
from careerflow.infrastructure.database.models import (
    AchievementModel,
    ApplicationModel,
    Base,
    InterviewModel,
    JobModel,
    ProfileModel,
)
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.main import create_app
from careerflow.seed import seed_session

# --- pure ------------------------------------------------------------------------------------------


def facts() -> tuple[list[SkillFact], list[AchievementFact]]:
    return (
        [SkillFact("s1", "Python", years=10, verified=True), SkillFact("s2", "Kubernetes", verified=True)],
        [
            AchievementFact("a1", "Scaled LLM platform", "serves 40 teams", ("Python", "LLM"), ("architecture", "leadership"), True),
            AchievementFact("a2", "Mentored juniors", "", (), ("mentoring",), False),
        ],
    )


JOB = JobFacts(
    "Principal AI Engineer",
    "Design distributed LLM platforms with RAG and strong observability; lead a team on Kubernetes.",
    ("Python", "Rust"),
    (),
)


def test_prep_is_grounded_in_the_job_and_the_profile() -> None:
    skills, achievements = facts()
    prep = prepare("system_design", JOB, "Contoso", skills, achievements, ["Rust", "Python"])
    assert prep.focus_areas[0].startswith("Requirements")
    assert [a.id for a in prep.relevant_achievements] == ["a1"]
    assert "Distributed systems: consistency, partitioning, failure modes" in prep.system_design_themes
    assert any(t.startswith("Observability") for t in prep.system_design_themes)
    assert any("Retrieval-augmented" in t for t in prep.ai_ml_topics) and any("LLM application design" in t for t in prep.ai_ml_topics)
    assert "Python" in prep.technical_topics and "Rust" in prep.technical_topics
    assert "No profile evidence for required skill: Rust" in prep.weak_spots  # honest about the gap
    assert [s.id for s in prep.leadership_stories] == ["a1", "a2"]
    assert any("Contoso" in q for q in prep.questions_to_ask) and any("architecture" in q for q in prep.questions_to_ask)


def test_interview_type_changes_the_focus() -> None:
    skills, achievements = facts()
    behavioral = prepare("behavioral", JOB, "C", skills, achievements)
    coding = prepare("coding", JOB, "C", skills, achievements)
    assert behavioral.focus_areas != coding.focus_areas
    assert any("STAR" in f for f in behavioral.focus_areas)
    assert any("algorithms" in f for f in coding.focus_areas)
    assert prepare("karaoke", JOB, "C", skills, achievements).focus_areas == ["Role fit and motivation"]


def test_empty_profile_still_produces_useful_questions() -> None:
    prep = prepare("recruiter", JobFacts("Analyst", "SQL reporting"), "Acme", [], [])
    assert prep.relevant_achievements == [] and prep.questions_to_ask and prep.focus_areas


# --- service / API ------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_session(s)
        yield s


def interview_for(session: Session, slug: str = "jordan-lee", company: str = "Lumen Robotics", kind: str = "system_design") -> tuple[ProfileModel, InterviewModel]:
    profile = session.scalars(select(ProfileModel).where(ProfileModel.slug == slug)).one()
    job = session.scalars(select(JobModel).where(JobModel.company == company)).one()
    app = ApplicationModel(profile_id=profile.id, job_id=job.id)
    session.add(app)
    session.flush()
    interview = InterviewModel(profile_id=profile.id, application_id=app.id, type=kind)
    session.add(interview)
    session.commit()
    return profile, interview


def test_without_ai_the_prep_is_deterministic_and_saved(session: Session) -> None:
    profile, interview = interview_for(session)
    data = InterviewPrepService(session, AiClient(DisabledProvider())).prepare(profile.id, interview.id)
    assert data["provenance"] == {"generator": "deterministic", "version": "interview-prep-v1"}
    assert "AI is disabled" in data["ai_note"] and data["ai_stories"] == []
    assert data["relevant_achievements"] and data["system_design_themes"]
    session.refresh(interview)
    assert interview.prep_json["interview_type"] == "system_design"  # stored on the interview


def test_suggestions_reference_real_profile_records(session: Session) -> None:
    profile, interview = interview_for(session)
    data = InterviewPrepService(session).prepare(profile.id, interview.id)
    real = {a.id for a in session.scalars(select(AchievementModel).where(AchievementModel.profile_id == profile.id))}
    refs = [a["id"] for a in data["relevant_achievements"]] + [a["id"] for a in data["leadership_stories"]]
    assert refs and set(refs) <= real


def test_ai_stories_are_validated_against_the_profile(session: Session) -> None:
    profile, interview = interview_for(session)
    evidence = next(i for i in collect_evidence(session, profile.id) if i.startswith("achievement:"))
    provider = FixtureProvider("fx").script(
        "interview_prep",
        json.dumps(
            {
                "focus_areas": ["Walk through the platform migration"],
                "questions_to_ask": ["How do you evaluate LLM quality in production?"],
                "story_suggestions": [
                    {"text": "Governed LLM platform story", "evidence_ids": [evidence]},
                    {"text": "Ran a 300-person org", "evidence_ids": ["experience:made-up"]},
                ],
            }
        ),
    )
    data = InterviewPrepService(session, AiClient(provider)).prepare(profile.id, interview.id)
    stories = {s["text"]: s for s in data["ai_stories"]}
    assert stories["Governed LLM platform story"]["basis"] == "evidence"
    assert stories["Ran a 300-person org"]["basis"] == "unverified" and stories["Ran a 300-person org"]["evidence_ids"] == []
    assert "Walk through the platform migration" in data["focus_areas"]
    assert "How do you evaluate LLM quality in production?" in data["questions_to_ask"]
    assert data["provenance"]["generator"] == "deterministic+ai" and data["provenance"]["prompt_version"] == "v1"


def test_ai_failure_keeps_the_deterministic_prep(session: Session) -> None:
    profile, interview = interview_for(session)
    provider = FixtureProvider().script("interview_prep", AiTimeoutError("slow"))
    data = InterviewPrepService(session, AiClient(provider, sleep=lambda _s: None)).prepare(profile.id, interview.id)
    assert "AI drafting failed" in data["ai_note"] and data["relevant_achievements"]


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    for dep in (profiles_session, tracking_session):
        app.dependency_overrides[dep] = lambda: session
    yield TestClient(app)


def test_api_prepares_and_isolates_by_profile(client: TestClient, session: Session) -> None:
    jordan, interview = interview_for(session)
    morgan = session.scalars(select(ProfileModel).where(ProfileModel.slug == "morgan-rivera")).one()
    url = f"/api/v1/profiles/{jordan.id}/interviews/{interview.id}/prepare"
    response = client.post(url)
    assert response.status_code == 200 and response.json()["questions_to_ask"]
    stored = client.get(f"/api/v1/profiles/{jordan.id}/interviews/{interview.id}").json()
    assert stored["prep_json"]["interview_type"] == "system_design"
    assert client.post(f"/api/v1/profiles/{morgan.id}/interviews/{interview.id}/prepare").status_code == 404
    assert client.get(f"/api/v1/profiles/{morgan.id}/interviews/{interview.id}").status_code == 404
    assert client.post(f"/api/v1/profiles/{jordan.id}/interviews/nope/prepare").status_code == 404
