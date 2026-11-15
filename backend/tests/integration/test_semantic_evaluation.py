import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from careerflow.application.ai.client import AiClient
from careerflow.application.evaluations.semantic import SemanticEvaluationService
from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.domain.evaluations.semantic import Claim, validate_claims
from careerflow.infrastructure.database.models import (
    Base,
    JobEvaluationModel,
    JobModel,
    ProfileModel,
)
from careerflow.infrastructure.llm.providers import DisabledProvider, FixtureProvider
from careerflow.seed import seed_session


@pytest.fixture
def session():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_session(s)
        yield s


def setup(session: Session, provider: object, slug: str = "jordan-lee", company: str = "Lumen Robotics"):  # type: ignore[no-untyped-def]
    base = EvaluationService(JobService(session), ProfileService(session))
    service = SemanticEvaluationService(base, AiClient(provider, sleep=lambda _s: None))  # type: ignore[arg-type]
    profile = session.scalars(select(ProfileModel).where(ProfileModel.slug == slug)).one()
    job = session.scalars(select(JobModel).where(JobModel.company == company)).one()
    return service, profile, job


def answer(evidence: dict[str, str], **extra: object) -> str:
    ids = list(evidence)
    experience = next(i for i in ids if i.startswith("experience:"))
    achievement = next(i for i in ids if i.startswith("achievement:"))
    return json.dumps(
        {
            "claims": [
                {"text": "Led an LLM platform", "kind": "strength", "basis": "evidence", "evidence_ids": [experience, achievement]},
                {"text": "Cloud depth suggests quick Azure ramp-up", "kind": "transferable", "basis": "inference", "evidence_ids": []},
                {"text": "Has run a 200-person org", "kind": "strength", "basis": "evidence", "evidence_ids": ["experience:does-not-exist"]},
                {"text": "No Kubernetes operator work", "kind": "gap", "basis": "unverified", "evidence_ids": []},
                {"text": "Great culture fit", "kind": "strength", "basis": "evidence", "evidence_ids": []},
            ],
            "dimension_scores": {"architecture_alignment": 0.9, "leadership_alignment": 0.8, "role_alignment": 0.0},
            "explanation": "Strong platform background.",
            **extra,
        }
    )


def test_every_positive_claim_has_real_evidence_or_is_flagged(session: Session) -> None:
    provider = FixtureProvider("fx")
    service, profile, job = setup(session, provider)
    evidence = service.evidence(profile.id)
    provider.script("semantic_evaluation", answer(evidence))

    row = service.evaluate(job.id, profile.id)

    assert row.prompt_version == "v1"
    assert (row.model_provider, row.model_name) == ("fixture", "fx")
    assert row.evaluator_version.startswith("hybrid-v1+")
    claims = row.claims_json
    assert len(claims) == 5
    for claim in claims:
        if claim["kind"] in ("strength", "transferable"):
            assert claim["basis"] in ("evidence", "inference", "unverified")
            if claim["basis"] == "evidence":
                assert claim["evidence_ids"], claim
                assert set(claim["evidence_ids"]) <= set(evidence), claim  # all resolve to real records
    by_text = {c["text"]: c for c in claims}
    assert by_text["Led an LLM platform"]["basis"] == "evidence"
    assert by_text["Cloud depth suggests quick Azure ramp-up"]["basis"] == "inference"
    hallucinated = by_text["Has run a 200-person org"]
    assert hallucinated["basis"] == "unverified" and hallucinated["evidence_ids"] == []
    assert by_text["Great culture fit"]["basis"] == "unverified"  # evidence claimed but none cited
    assert any("[evidence:" in s for s in row.strengths)
    assert any("[unverified]" in s for s in row.strengths)
    assert any("[inference]" in s for s in row.transferable_matches)


def test_semantic_scores_fill_only_semantic_dimensions(session: Session) -> None:
    provider = FixtureProvider()
    service, profile, job = setup(session, provider)
    provider.script("semantic_evaluation", answer(service.evidence(profile.id)))
    row = service.evaluate(job.id, profile.id)
    scores = row.dimension_scores_json
    assert scores["architecture_alignment"] == 0.9 and scores["leadership_alignment"] == 0.8
    assert scores["role_alignment"] > 0.5  # the model's "0.0" for a rule-scored dimension was ignored
    assert not any(u.startswith("architecture_alignment") for u in row.unknowns)


def test_deterministic_blockers_always_win(session: Session) -> None:
    provider = FixtureProvider()
    service, profile, job = setup(session, provider, company="Smokestack Tobacco")
    provider.script(
        "semantic_evaluation",
        json.dumps({"claims": [], "dimension_scores": {"architecture_alignment": 1.0, "leadership_alignment": 1.0}}),
    )
    row = service.evaluate(job.id, profile.id)
    assert row.blockers  # still blocked (excluded company, remote required)
    assert row.overall_score <= 0.2


def test_ai_disabled_returns_the_unchanged_deterministic_evaluation(session: Session) -> None:
    service, profile, job = setup(session, DisabledProvider())
    expected = service.base.get_job_evaluation(job.id, profile.id)  # seeded deterministic row
    assert expected is not None
    row = service.evaluate(job.id, profile.id)
    assert row.evaluator_version == expected.evaluator_version == "deterministic-v2.0"
    assert row.prompt_version is None and row.claims_json == []
    assert (row.overall_score, row.dimension_scores_json, row.strengths) == (
        expected.overall_score, expected.dimension_scores_json, expected.strengths,
    )  # fmt: skip


def test_history_is_append_only(session: Session) -> None:
    provider = FixtureProvider()
    service, profile, job = setup(session, provider)
    provider.script("semantic_evaluation", answer(service.evidence(profile.id)))
    before = len(list(session.scalars(select(JobEvaluationModel))))
    service.evaluate(job.id, profile.id)
    service.evaluate(job.id, profile.id)
    assert len(list(session.scalars(select(JobEvaluationModel)))) == before + 2


def test_evidence_catalogue_is_profile_scoped(session: Session) -> None:
    provider = FixtureProvider()
    service, jordan, _ = setup(session, provider)
    morgan = session.scalars(select(ProfileModel).where(ProfileModel.slug == "morgan-rivera")).one()
    a, b = service.evidence(jordan.id), service.evidence(morgan.id)
    private = ("experience:", "achievement:")  # skills are a shared catalog, records are not
    assert not {k for k in a if k.startswith(private)} & {k for k in b if k.startswith(private)}
    assert any(k.startswith("skill:") for k in a)
    assert any("Azure" in v for v in a.values()) and not any("Azure" in v for v in b.values())


def test_validate_claims_unit() -> None:
    known = {"experience:1", "skill:2"}
    checked = validate_claims(
        [
            Claim("ok", "strength", "evidence", ("experience:1", "skill:2")),
            Claim("partly fake", "strength", "evidence", ("experience:1", "skill:zzz")),
            Claim("bad basis", "transferable", "magic", ("experience:1",)),
            Claim("gap", "gap", "unverified"),
        ],
        known,
    )
    assert [c.basis for c in checked] == ["evidence", "unverified", "unverified", "unverified"]
    assert checked[1].evidence_ids == () and "does not exist" in (checked[1].note or "")
