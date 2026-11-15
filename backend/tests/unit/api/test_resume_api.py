from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.resume import get_session as resume_session
from careerflow.infrastructure.database.models import Base, JobModel
from careerflow.main import create_app

API = "/api/v1"


@pytest.fixture
def env() -> Generator[tuple[TestClient, Session]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    app = create_app()
    for dep in (profiles_session, resume_session):
        app.dependency_overrides[dep] = lambda: session
    yield TestClient(app), session
    session.close()


def profile(client: TestClient, slug: str) -> dict[str, str]:
    pid = client.post(f"{API}/profiles", json={"slug": slug, "display_name": slug}).json()["id"]
    exp = client.post(f"{API}/profiles/{pid}/experiences", json={"organization": "Org", "title": "Eng"}).json()["id"]
    ach = client.post(f"{API}/profiles/{pid}/achievements", json={"title": "Shipped", "experience_id": exp}).json()["id"]
    fam = client.post(f"{API}/profiles/{pid}/role-families", json={"name": "AI"}).json()["id"]
    return {"id": pid, "exp": exp, "ach": ach, "fam": fam}


def job(session: Session) -> str:
    row = JobModel(title="J", company="C", description_text="d")
    session.add(row)
    session.commit()
    return row.id


def variant_body(p: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {
        "name": "AI Architect", "role_family_id": p["fam"], "summary_strategy": "lead with platform work",
        "preferred_skill_categories": ["ai"], "selected_experience_ids": [p["exp"]], "selected_achievement_ids": [p["ach"]],
        **extra,
    }  # fmt: skip


def test_templates_include_a_default(env: tuple[TestClient, Session]) -> None:
    client, _ = env
    templates = client.get(f"{API}/resume-templates").json()
    assert [t["name"] for t in templates] == ["Plain Markdown"] and templates[0]["format"] == "markdown"


def test_variant_crud_and_default_template(env: tuple[TestClient, Session]) -> None:
    client, _ = env
    a = profile(client, "a")
    created = client.post(f"{API}/profiles/{a['id']}/resume-variants", json=variant_body(a))
    assert created.status_code == 201
    body = created.json()
    assert body["template_id"] and body["selected_achievement_ids"] == [a["ach"]]
    vid = body["id"]
    updated = client.put(f"{API}/profiles/{a['id']}/resume-variants/{vid}", json=variant_body(a, name="Renamed"))
    assert updated.json()["name"] == "Renamed"
    assert [v["id"] for v in client.get(f"{API}/profiles/{a['id']}/resume-variants").json()] == [vid]
    assert client.delete(f"{API}/profiles/{a['id']}/resume-variants/{vid}").status_code == 204
    assert client.get(f"{API}/profiles/{a['id']}/resume-variants/{vid}").status_code == 404


def test_variants_reject_another_profiles_records(env: tuple[TestClient, Session]) -> None:
    client, _ = env
    a, b = profile(client, "a"), profile(client, "b")
    for bad in ({"role_family_id": a["fam"]}, {"selected_experience_ids": [a["exp"]]}, {"selected_achievement_ids": [a["ach"]]}):
        body = {"name": "X", "selected_experience_ids": [], "selected_achievement_ids": [], **bad}
        response = client.post(f"{API}/profiles/{b['id']}/resume-variants", json=body)
        assert response.status_code == 422 and "does not belong" in response.text
    assert client.post(f"{API}/profiles/{b['id']}/resume-variants", json={"name": "X", "template_id": "nope"}).status_code == 422


def test_variants_and_packages_are_isolated_between_profiles(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = profile(client, "a"), profile(client, "b")
    variant = client.post(f"{API}/profiles/{a['id']}/resume-variants", json=variant_body(a)).json()["id"]
    job_id = job(session)
    package = client.put(f"{API}/profiles/{a['id']}/packages/by-job/{job_id}", json={"resume_variant_id": variant}).json()

    base = f"{API}/profiles/{b['id']}"
    assert client.get(f"{base}/resume-variants").json() == []
    assert client.get(f"{base}/resume-variants/{variant}").status_code == 404
    assert client.put(f"{base}/resume-variants/{variant}", json={"name": "hijack"}).status_code == 404
    assert client.delete(f"{base}/resume-variants/{variant}").status_code == 404
    assert client.get(f"{base}/packages").json() == []
    assert client.get(f"{base}/packages/by-job/{job_id}").json() is None
    assert client.delete(f"{base}/packages/{package['id']}").status_code == 404
    assert client.put(f"{base}/packages/by-job/{job_id}", json={"resume_variant_id": variant}).status_code == 404  # not B's variant
    assert client.get(f"{API}/profiles/{a['id']}/resume-variants/{variant}").json()["name"] == "AI Architect"


def test_package_upsert_validation_and_variant_deletion(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a, b = profile(client, "a"), profile(client, "b")
    job_id = job(session)
    url = f"{API}/profiles/{a['id']}/packages/by-job/{job_id}"
    assert client.get(url).json() is None
    first = client.put(url, json={"recommended_achievement_ids": [a["ach"]], "tailoring_notes": ["lead with X"], "missing_evidence": ["Kubernetes"]})
    assert first.status_code == 200 and first.json()["status"] == "DRAFT"
    second = client.put(url, json={"summary_suggestion": "new"})
    assert second.json()["id"] == first.json()["id"] and second.json()["summary_suggestion"] == "new"  # one package per job
    assert len(client.get(f"{API}/profiles/{a['id']}/packages").json()) == 1
    assert client.put(url, json={"recommended_achievement_ids": [b["ach"]]}).status_code == 422
    assert client.put(f"{API}/profiles/{a['id']}/packages/by-job/nope", json={}).status_code == 404

    variant = client.post(f"{API}/profiles/{a['id']}/resume-variants", json=variant_body(a)).json()["id"]
    client.put(url, json={"resume_variant_id": variant})
    client.delete(f"{API}/profiles/{a['id']}/resume-variants/{variant}")
    assert client.get(url).json()["resume_variant_id"] is None  # deleting a variant detaches, never deletes, the package
    assert client.delete(f"{API}/profiles/{a['id']}/packages/{first.json()['id']}").status_code == 204


def test_variants_and_packages_survive_export_and_import(env: tuple[TestClient, Session]) -> None:
    client, session = env
    a = profile(client, "a")
    variant = client.post(f"{API}/profiles/{a['id']}/resume-variants", json=variant_body(a)).json()["id"]
    job_id = job(session)
    client.put(
        f"{API}/profiles/{a['id']}/packages/by-job/{job_id}",
        json={"resume_variant_id": variant, "recommended_achievement_ids": [a["ach"]], "recommended_skill_order": ["Python"], "cover_letter_notes": ["mention scale"]},
    )
    exported = client.get(f"{API}/profiles/{a['id']}/export").json()
    assert exported["resume_variants"][0]["achievement_indexes"] == [0] and exported["resume_variants"][0]["role_family_index"] == 0
    assert exported["resume_variants"][0]["template_name"] == "Plain Markdown"
    assert exported["application_packages"][0]["job_id"] == job_id and exported["application_packages"][0]["variant_index"] == 0

    exported["profile"]["slug"] = "a-copy"
    imported = client.post(f"{API}/profiles/import", json=exported)
    assert imported.status_code == 201, imported.text
    new_id = imported.json()["id"]
    again = client.get(f"{API}/profiles/{new_id}/export").json()
    exported["profile"]["slug"] = "a-copy"
    assert again == exported

    new_variant = client.get(f"{API}/profiles/{new_id}/resume-variants").json()[0]
    new_achievement = client.get(f"{API}/profiles/{new_id}/achievements").json()[0]["id"]
    assert new_variant["id"] != variant and new_variant["selected_achievement_ids"] == [new_achievement] != [a["ach"]]
    package = client.get(f"{API}/profiles/{new_id}/packages/by-job/{job_id}").json()
    assert package["resume_variant_id"] == new_variant["id"] and package["recommended_achievement_ids"] == [new_achievement]


def test_import_skips_packages_for_unknown_jobs(env: tuple[TestClient, Session]) -> None:
    client, _ = env
    payload = {
        "profile": {"slug": "x", "display_name": "X"},
        "application_packages": [{"job_id": "does-not-exist", "tailoring_notes": ["n"]}],
    }
    created = client.post(f"{API}/profiles/import", json=payload)
    assert created.status_code == 201
    assert client.get(f"{API}/profiles/{created.json()['id']}/packages").json() == []
