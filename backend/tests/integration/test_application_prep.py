from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.resume import get_session as resume_session
from careerflow.application.ai.client import AiClient
from careerflow.application.applications.prepare import PreparationService
from careerflow.domain.ai.ports import AiTimeoutError
from careerflow.domain.applications.tailoring import (
    AchievementFact,
    JobFacts,
    SkillFact,
    VariantFact,
    recommend,
)
from careerflow.infrastructure.database.models import (
    AchievementModel,
    ApplicationPackageModel,
    Base,
    JobModel,
    JobRequirementModel,
    ProfileModel,
    ResumeVariantModel,
)
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.main import create_app
from careerflow.seed import seed_session

# --- pure recommendation logic ---------------------------------------------------------------------


def facts() -> tuple[list[SkillFact], list[AchievementFact], list[VariantFact]]:
    skills = [
        SkillFact("s1", "Python", category="language", years=12, verified=True),
        SkillFact("s2", "Azure", ("Microsoft Azure",), "cloud", 6, True),
        SkillFact("s3", "Tableau", category="viz", years=2, verified=False),
    ]
    achievements = [
        AchievementFact("a1", "LLM platform", "Built governed LLM apps", ("Python", "LLM"), ("architecture",), True),
        AchievementFact("a2", "Dashboard revamp", "Reworked reporting", ("Tableau",), (), False),
        AchievementFact("a3", "Office party", "Organised it", (), (), True),
    ]
    variants = [
        VariantFact("v1", "AI Architect", "AI Architect", ("cloud",), ("a1",)),
        VariantFact("v2", "Analyst", "Data Analyst", ("viz",), ("a2",)),
    ]
    return skills, achievements, variants


def test_recommendation_picks_variant_achievements_and_orders_skills() -> None:
    skills, achievements, variants = facts()
    job = JobFacts("Principal AI Architect", "Design LLM platforms on Azure with Python.", ("Python", "LLM"), ())
    rec = recommend(job, skills, achievements, variants)
    assert rec.variant_id == "v1"
    assert rec.achievement_ids == ["a1"]  # irrelevant/unmatched achievements are never recommended
    # job-relevant skills first; the chosen variant prefers "cloud", so Azure leads Python
    assert rec.skill_order == ["Azure", "Python", "Tableau"]
    assert any(n.evidence_ids == ("achievement:a1",) for n in rec.cover_letter_notes)
    assert rec.summary_suggestion is not None and "LLM platform" in rec.summary_suggestion
    assert not rec.warnings  # everything used is verified


def test_missing_evidence_and_unverified_warnings() -> None:
    skills, achievements, variants = facts()
    job = JobFacts("Data Analyst", "Reporting in Tableau, Kubernetes and Rust.", ("Tableau", "Kubernetes"), ())
    rec = recommend(job, skills, achievements, variants, known_skill_names=["Rust", "Python", "Kubernetes"])
    assert rec.variant_id == "v2"
    assert "No profile evidence for required skill: Kubernetes" in rec.missing_evidence
    assert "The job mentions Rust, which your profile does not show" in rec.missing_evidence
    assert not any("Tableau" in m for m in rec.missing_evidence)  # the profile does have it
    assert any("'Dashboard revamp' is not marked verified" in w for w in rec.warnings)
    assert any("Skill 'Tableau' is not marked verified" in w for w in rec.warnings)


def test_recommendation_never_invents_ids() -> None:
    skills, achievements, variants = facts()
    rec = recommend(JobFacts("AI Architect", "LLM Azure Python Tableau", ("LLM",), ()), skills, achievements, variants)
    known = {a.id for a in achievements}
    assert set(rec.achievement_ids) <= known
    for note in [*rec.tailoring_notes, *rec.cover_letter_notes]:
        for evidence in note.evidence_ids:
            kind, _, ident = evidence.partition(":")
            assert ident in ({a.id for a in achievements} | {s.id for s in skills}), evidence


def test_no_variants_or_data_is_handled() -> None:
    rec = recommend(JobFacts("Anything", "text"), [], [], [])
    assert rec.variant_id is None and rec.achievement_ids == [] and rec.summary_suggestion is None


# --- service + API ---------------------------------------------------------------------------------------


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_session(s)
        yield s


def ids(session: Session) -> tuple[ProfileModel, JobModel]:
    profile = session.scalars(select(ProfileModel).where(ProfileModel.slug == "jordan-lee")).one()
    job = session.scalars(select(JobModel).where(JobModel.company == "Lumen Robotics")).one()
    return profile, job


def package_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(ApplicationPackageModel)) or 0)


def ai_answer(session: Session, profile: ProfileModel) -> str:
    achievement = session.scalars(select(AchievementModel).where(AchievementModel.profile_id == profile.id)).first()
    assert achievement is not None
    return json.dumps(
        {
            "summary_suggestion": "AI summary",
            "cover_letter_points": [
                {"text": "Led a governed LLM platform", "evidence_ids": [f"achievement:{achievement.id}"]},
                {"text": "Managed 400 engineers", "evidence_ids": ["experience:made-up"]},
                {"text": "Is a great culture fit", "evidence_ids": []},
            ],
            "outreach_draft": "Hello, I would love to discuss the platform role.",
        }
    )


def test_propose_is_read_only_and_deterministic_without_ai(session: Session) -> None:
    profile, job = ids(session)
    proposal = PreparationService(session, AiClient(DisabledProvider())).propose(profile.id, job.id)
    assert proposal.persisted is False and package_count(session) == 0
    assert proposal.provenance == {"generator": "deterministic", "version": "tailor-v1"}
    assert "AI is disabled" in (proposal.ai_note or "")
    assert proposal.outreach_draft is None
    assert proposal.recommended_achievement_ids  # Jordan's platform achievement matches this job
    assert proposal.existing_package_id is None


def test_ai_claims_are_validated_against_real_evidence(session: Session) -> None:
    profile, job = ids(session)
    provider = FixtureProvider("fx").script("application_prep", ai_answer(session, profile))
    proposal = PreparationService(session, AiClient(provider)).propose(profile.id, job.id)
    ai_claims = {c.text: c for c in proposal.claims if c.source == "ai"}
    assert ai_claims["Led a governed LLM platform"].basis == "evidence"
    fabricated = ai_claims["Managed 400 engineers"]
    assert fabricated.basis == "unverified" and fabricated.evidence_ids == []
    assert ai_claims["Is a great culture fit"].basis == "unverified"
    assert "Managed 400 engineers [unverified: not backed by your profile]" in proposal.cover_letter_notes
    assert proposal.outreach_draft is not None and "never sends" in proposal.outreach_draft
    assert proposal.provenance["generator"] == "deterministic+ai" and proposal.provenance["prompt_version"] == "v1"
    assert (proposal.provenance["provider"], proposal.provenance["model"]) == ("fixture", "fx")
    assert package_count(session) == 0  # still nothing stored


def test_ai_failure_degrades_to_the_deterministic_proposal(session: Session) -> None:
    profile, job = ids(session)
    provider = FixtureProvider().script("application_prep", AiTimeoutError("slow"))
    proposal = PreparationService(session, AiClient(provider, sleep=lambda _s: None)).propose(profile.id, job.id)
    assert "AI drafting failed" in (proposal.ai_note or "") and proposal.recommended_achievement_ids
    assert package_count(session) == 0


def test_every_deterministic_claim_cites_real_records_or_is_flagged_advice(session: Session) -> None:
    profile, job = ids(session)
    proposal = PreparationService(session).propose(profile.id, job.id)
    from careerflow.application.evaluations.semantic import collect_evidence

    real = set(collect_evidence(session, profile.id))
    for claim in proposal.claims:
        assert claim.basis in ("evidence", "inference")
        if claim.basis == "evidence":
            assert claim.evidence_ids and set(claim.evidence_ids) <= real, claim
        else:
            assert claim.evidence_ids == []


def test_missing_evidence_uses_extracted_requirements(session: Session) -> None:
    profile, job = ids(session)
    session.add(JobRequirementModel(job_id=job.id, type="skill", normalized_text="Kubernetes", source_text="k8s", required_level="REQUIRED", category="skill"))
    session.commit()
    proposal = PreparationService(session).propose(profile.id, job.id)
    assert "No profile evidence for required skill: Kubernetes" in proposal.missing_evidence


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    for dep in (profiles_session, resume_session):
        app.dependency_overrides[dep] = lambda: session
    yield TestClient(app)


def test_nothing_is_persisted_until_the_user_approves(client: TestClient, session: Session) -> None:
    profile, job = ids(session)
    base = f"/api/v1/profiles/{profile.id}/jobs/{job.id}"
    proposal = client.post(f"{base}/prepare")
    assert proposal.status_code == 200
    body = proposal.json()
    assert body["persisted"] is False and body["claims"]
    assert package_count(session) == 0
    assert client.get(f"/api/v1/profiles/{profile.id}/packages/by-job/{job.id}").json() is None

    approved = client.post(
        f"{base}/prepare/approve",
        json={
            "resume_variant_id": body["resume_variant_id"],
            "recommended_achievement_ids": body["recommended_achievement_ids"],
            "recommended_skill_order": body["recommended_skill_order"],
            "summary_suggestion": "my edited summary",
            "tailoring_notes": body["tailoring_notes"],
            "missing_evidence": body["missing_evidence"],
            "cover_letter_notes": body["cover_letter_notes"],
            "provenance": body["provenance"],
        },
    )
    assert approved.status_code == 200, approved.text
    package = approved.json()
    assert package["status"] == "APPROVED" and package["approved_at"] and package["summary_suggestion"] == "my edited summary"
    assert package["provenance_json"]["generator"] == "deterministic"
    assert package_count(session) == 1
    assert client.post(f"{base}/prepare").json()["existing_package_id"] == package["id"]
    assert package_count(session) == 1  # re-preparing still writes nothing


def test_approve_rejects_foreign_evidence_and_unknown_records(client: TestClient, session: Session) -> None:
    jordan, job = ids(session)
    morgan = session.scalars(select(ProfileModel).where(ProfileModel.slug == "morgan-rivera")).one()
    morgan_achievement = session.scalars(select(AchievementModel).where(AchievementModel.profile_id == morgan.id)).first()
    assert morgan_achievement is not None
    url = f"/api/v1/profiles/{jordan.id}/jobs/{job.id}/prepare/approve"
    assert client.post(url, json={"recommended_achievement_ids": [morgan_achievement.id]}).status_code == 422
    assert client.post(f"/api/v1/profiles/{jordan.id}/jobs/nope/prepare/approve", json={}).status_code == 404
    assert client.post(f"/api/v1/profiles/nope/jobs/{job.id}/prepare").status_code == 404
    assert package_count(session) == 0


def test_variant_choice_follows_the_job(client: TestClient, session: Session) -> None:
    profile, job = ids(session)
    session.add_all(
        [
            ResumeVariantModel(profile_id=profile.id, name="Generic", preferred_skill_categories=[]),
            ResumeVariantModel(profile_id=profile.id, name="AI Engineer variant", preferred_skill_categories=["ai"]),
        ]
    )
    session.commit()
    body = client.post(f"/api/v1/profiles/{profile.id}/jobs/{job.id}/prepare").json()
    chosen = session.get(ResumeVariantModel, body["resume_variant_id"])
    assert chosen is not None and chosen.name == "AI Engineer variant"


def test_there_is_no_send_capability() -> None:
    import careerflow.application.applications.prepare as prepare

    names = {n.lower() for n in dir(prepare)}
    assert not any(word in n for n in names for word in ("smtp", "sendmail", "send_email", "send_message"))
