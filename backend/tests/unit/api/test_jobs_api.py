from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.jobs import get_session
from careerflow.application.profiles.service import ProfileService
from careerflow.infrastructure.database.models import (
    Base,
    JobStatusHistoryModel,
    ProfileModel,
)
from careerflow.main import create_app

JOB = {
    "title": "Principal AI Engineer",
    "company": "Acme Labs",
    "description_text": "Build LLM applications with Python.",
    "remote_type": "REMOTE",
    "salary_min": 180000,
    "salary_max": 220000,
    "salary_currency": "USD",
    "salary_period": "YEAR",
}


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine) -> Generator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app()

    def override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)


@pytest.fixture
def profiles(engine) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        service = ProfileService(session)
        a = service.create_profile({"slug": "a", "display_name": "Profile A"})
        b = service.create_profile({"slug": "b", "display_name": "Profile B"})
        return a.id, b.id


def import_job(client: TestClient, **overrides: Any) -> str:
    response = client.post("/api/v1/jobs/import", json={**JOB, **overrides})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_import_requires_description(client: TestClient) -> None:
    body = {k: v for k, v in JOB.items() if k != "description_text"}
    response = client.post("/api/v1/jobs/import", json=body)
    assert response.status_code == 422
    assert any("description_text" in e["loc"] for e in response.json()["detail"])


def test_import_validates_enums_and_salary(client: TestClient) -> None:
    assert client.post("/api/v1/jobs/import", json={**JOB, "remote_type": "MOON"}).status_code == 422
    assert (
        client.post("/api/v1/jobs/import", json={**JOB, "salary_period": "FORTNIGHT"}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/jobs/import", json={**JOB, "salary_min": 9, "salary_max": 1}).status_code
        == 422
    )
    assert client.post("/api/v1/jobs/import", json={**JOB, "description_text": ""}).status_code == 422


def test_import_with_source_and_requirements(client: TestClient) -> None:
    job_id = import_job(
        client,
        canonical_url="https://example.com/jobs/1",
        source={"adapter": "manual", "raw_payload": {"pasted": True}},
        requirements=[{"type": "skill", "normalized_text": "Python", "source_text": "Python"}],
    )
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "READY_FOR_REVIEW"
    assert job["canonical_url"] == "https://example.com/jobs/1"
    assert client.get(f"/api/v1/jobs/{job_id}/sources").json()[0]["adapter"] == "manual"
    assert client.get(f"/api/v1/jobs/{job_id}/requirements").json()[0]["normalized_text"] == "Python"


def test_partial_update_and_unknown_job(client: TestClient) -> None:
    job_id = import_job(client)
    response = client.patch(f"/api/v1/jobs/{job_id}", json={"title": "Staff Engineer"})
    assert response.status_code == 200
    assert response.json()["title"] == "Staff Engineer"
    assert response.json()["company"] == "Acme Labs"
    assert client.get("/api/v1/jobs/missing").status_code == 404


def test_openapi_has_typed_job_schemas(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert {"JobOutput", "JobImport", "JobEvaluationOutput", "WorkflowStatusOutput"} <= set(schemas)
    for path, methods in spec["paths"].items():
        if path.startswith("/api/v1/jobs"):
            for operation in methods.values():
                content = operation.get("responses", {}).get("200", {}).get("content", {})
                for media in content.values():
                    assert media["schema"] != {"type": "object"}, path


def test_workflow_is_per_profile(client: TestClient, profiles: tuple[str, str]) -> None:
    a, b = profiles
    job_id = import_job(client)
    response = client.post(f"/api/v1/jobs/{job_id}/shortlist", json={"profile_id": a, "reason": "ok"})
    assert response.status_code == 200
    assert response.json()["status"] == "SHORTLISTED"
    assert client.get(f"/api/v1/jobs/{job_id}/workflow", params={"profile_id": a}).json()["status"] == "SHORTLISTED"
    assert client.get(f"/api/v1/jobs/{job_id}/workflow", params={"profile_id": b}).json()["status"] == "READY_FOR_REVIEW"
    assert client.get(f"/api/v1/jobs/{job_id}/status-history", params={"profile_id": b}).json() == []
    history = client.get(f"/api/v1/jobs/{job_id}/status-history", params={"profile_id": a}).json()
    assert len(history) == 1
    assert history[0]["profile_id"] == a
    assert history[0]["old_status"] == "READY_FOR_REVIEW"
    assert history[0]["new_status"] == "SHORTLISTED"
    assert history[0]["actor"] == "user"
    assert history[0]["reason"] == "ok"


def test_forbidden_transition_returns_409_and_writes_nothing(
    client: TestClient, engine, profiles: tuple[str, str]  # type: ignore[no-untyped-def]
) -> None:
    a, _ = profiles
    job_id = import_job(client)
    assert client.post(f"/api/v1/jobs/{job_id}/reject", json={"profile_id": a}).status_code == 200
    again = client.post(f"/api/v1/jobs/{job_id}/reject", json={"profile_id": a})
    assert again.status_code == 409
    shortlist = client.post(f"/api/v1/jobs/{job_id}/shortlist", json={"profile_id": a})
    assert shortlist.status_code == 409
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(JobStatusHistoryModel))
    assert count == 1  # only the successful rejection


def test_workflow_unknown_profile_or_job_is_404(client: TestClient, profiles: tuple[str, str]) -> None:
    a, _ = profiles
    job_id = import_job(client)
    assert client.post(f"/api/v1/jobs/{job_id}/save", json={"profile_id": "nope"}).status_code == 404
    assert client.post("/api/v1/jobs/nope/save", json={"profile_id": a}).status_code == 404
    assert client.post(f"/api/v1/jobs/{job_id}/save", json={}).status_code == 422


def test_evaluation_history_is_append_only_and_profile_scoped(
    client: TestClient, profiles: tuple[str, str]
) -> None:
    a, b = profiles
    job_id = import_job(client)
    first = client.post(f"/api/v1/jobs/{job_id}/evaluate", json={"profile_id": a})
    assert first.status_code == 201
    assert first.json()["evaluator_version"] == "deterministic-v2.0"
    client.post(f"/api/v1/jobs/{job_id}/evaluations", json={"profile_id": a})
    client.post(f"/api/v1/jobs/{job_id}/evaluate", json={"profile_id": b})
    all_rows = client.get(f"/api/v1/jobs/{job_id}/evaluations").json()
    only_a = client.get(f"/api/v1/jobs/{job_id}/evaluations", params={"profile_id": a}).json()
    assert len(all_rows) == 3
    assert len(only_a) == 2
    assert {row["profile_id"] for row in only_a} == {a}
    latest = client.get(f"/api/v1/jobs/{job_id}/evaluations/latest", params={"profile_id": b}).json()
    assert latest["profile_id"] == b


def test_profile_rows_are_isolated(client: TestClient, engine, profiles: tuple[str, str]) -> None:  # type: ignore[no-untyped-def]
    a, b = profiles
    job_id = import_job(client)
    client.post(f"/api/v1/jobs/{job_id}/save", json={"profile_id": a})
    with Session(engine) as session:
        assert session.get(ProfileModel, b) is not None
        rows = session.scalars(
            select(JobStatusHistoryModel).where(JobStatusHistoryModel.profile_id == b)
        ).all()
    assert rows == []
