import re

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from careerflow.application.evaluations.service import EvaluationService
from careerflow.application.jobs.service import JobService
from careerflow.application.profiles.service import ProfileService
from careerflow.infrastructure.database.models import (
    Base,
    JobModel,
    ProfileModel,
    ProfileSkillModel,
    SkillModel,
)
from careerflow.seed import JOBS, PROFILES, seed_session


@pytest.fixture
def session():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_session(s)
        yield s


def count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_is_idempotent(session: Session) -> None:
    before = (count(session, ProfileModel), count(session, JobModel), count(session, SkillModel))
    seed_session(session)
    seed_session(session)
    assert (count(session, ProfileModel), count(session, JobModel), count(session, SkillModel)) == before
    assert before[0] == len(PROFILES) == 2
    assert before[1] == len(JOBS)
    assert count(session, ProfileSkillModel) == sum(len(p["skills"]) for p in PROFILES)


def test_seed_contains_only_fictional_data() -> None:
    text = repr(PROFILES) + repr(JOBS)
    assert not re.search(r"[\w.]+@[\w.]+\.\w+", text)
    assert not re.search(r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b", text)
    assert all(j["canonical_url"].startswith("https://example.com/") for j in JOBS)


def evaluate_all(session: Session) -> dict[tuple[str, str], object]:
    service = EvaluationService(JobService(session), ProfileService(session))
    profiles = {p.slug: p for p in session.scalars(select(ProfileModel))}
    jobs = {j.company: j for j in session.scalars(select(JobModel))}
    return {
        (slug, company): service.evaluate_job_for_profile(job.id, profile.id)
        for slug, profile in profiles.items()
        for company, job in jobs.items()
    }


def test_four_scenarios(session: Session) -> None:
    ev: dict[tuple[str, str], object] = evaluate_all(session)

    def score(slug: str, company: str) -> float:
        return float(ev[(slug, company)].overall_score)  # type: ignore[attr-defined]

    def blockers(slug: str, company: str) -> list[str]:
        return list(ev[(slug, company)].blockers)  # type: ignore[attr-defined]

    # strong A / weak B
    assert score("jordan-lee", "Lumen Robotics") > 0.7
    assert score("jordan-lee", "Lumen Robotics") > score("morgan-rivera", "Lumen Robotics") + 0.2
    # weak A / strong B
    assert score("morgan-rivera", "Harbor Retail Group") > 0.7
    assert score("morgan-rivera", "Harbor Retail Group") > score("jordan-lee", "Harbor Retail Group") + 0.2
    # blocked by hard preference
    jordan_blockers = blockers("jordan-lee", "Smokestack Tobacco")
    assert any("excluded" in b for b in jordan_blockers)
    assert any("Remote work required" in b for b in jordan_blockers)
    assert score("jordan-lee", "Smokestack Tobacco") <= 0.2
    assert not blockers("morgan-rivera", "Harbor Retail Group")
    # transferable-but-not-exact: Morgan lacks Azure but holds AWS (same cloud category)
    matches = ev[("morgan-rivera", "Blue Meridian Health")].transferable_matches  # type: ignore[attr-defined]
    assert any("Azure" in m and "AWS" in m for m in matches)


def test_seed_evaluates_each_job_once_per_profile(session: Session) -> None:
    from careerflow.infrastructure.database.models import JobEvaluationModel

    expected = len(JOBS) * len(PROFILES)
    assert count(session, JobEvaluationModel) == expected
    seed_session(session)
    assert count(session, JobEvaluationModel) == expected
