import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from careerflow.demo import (
    DemoModeRequiredError,
    ExternalWritesDisabledError,
    ensure_external_writes_allowed,
    external_writes_allowed,
    main,
    reset_demo_data,
)
from careerflow.infrastructure.database.models import (
    Base,
    JobEvaluationModel,
    JobModel,
    JobStatusHistoryModel,
    ProfileJobModel,
    ProfileModel,
)
from careerflow.main import create_app
from careerflow.seed import seed_session
from careerflow.settings import Settings, get_settings


def snapshot(session: Session) -> dict[str, object]:
    return {
        "profiles": sorted(session.scalars(select(ProfileModel.slug))),
        "jobs": sorted(session.scalars(select(JobModel.title))),
        "evaluations": session.scalar(select(func.count()).select_from(JobEvaluationModel)),
        "workflow": session.scalar(select(func.count()).select_from(ProfileJobModel)),
        "history": session.scalar(select(func.count()).select_from(JobStatusHistoryModel)),
    }


def test_reset_restores_the_seeded_state() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_session(session)
        known = snapshot(session)

        # user activity: new profile, new job, workflow change, deleted seed job
        from careerflow.application.jobs.workflow import JobWorkflowService
        from careerflow.domain.jobs.workflow import WorkflowStatus

        profile = session.scalars(select(ProfileModel)).first()
        job = session.scalars(select(JobModel)).first()
        assert profile and job
        JobWorkflowService(session).transition(profile.id, job.id, WorkflowStatus.SHORTLISTED)
        session.add(ProfileModel(slug="mine", display_name="Mine"))
        session.add(JobModel(title="Mine", company="Mine", description_text="x"))
        session.commit()
        assert snapshot(session) != known

        reset_demo_data(session, Settings(demo_mode=True))
        assert snapshot(session) == known


def test_reset_refuses_outside_demo_mode() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_session(session)
        session.add(ProfileModel(slug="real", display_name="Real Person"))
        session.commit()
        with pytest.raises(DemoModeRequiredError):
            reset_demo_data(session, Settings(demo_mode=False))
        assert "real" in snapshot(session)["profiles"]  # type: ignore[operator]


def test_cli_refuses_without_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    try:
        assert main(["reset"]) == 1
        assert main(["nonsense"]) == 2
    finally:
        get_settings.cache_clear()


def test_external_write_guard() -> None:
    assert external_writes_allowed(Settings(demo_mode=False))
    ensure_external_writes_allowed(Settings(demo_mode=False))
    assert not external_writes_allowed(Settings(demo_mode=True))
    with pytest.raises(ExternalWritesDisabledError):
        ensure_external_writes_allowed(Settings(demo_mode=True))


@pytest.mark.parametrize("flag", [True, False])
def test_config_endpoint_reports_demo_mode(monkeypatch: pytest.MonkeyPatch, flag: bool) -> None:
    monkeypatch.setenv("DEMO_MODE", "true" if flag else "false")
    get_settings.cache_clear()
    try:
        body = TestClient(create_app()).get("/api/v1/config").json()
    finally:
        get_settings.cache_clear()
    assert body == {"demo_mode": flag, "auth_mode": "local", "external_writes_enabled": not flag}
