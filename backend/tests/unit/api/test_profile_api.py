from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.profiles import get_session
from careerflow.infrastructure.database.models import Base
from careerflow.main import create_app
from careerflow.seed import seed_session

API = "/api/v1/profiles"


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    app = create_app()

    def override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)


def make_profile(client: TestClient, slug: str) -> str:
    response = client.post(API, json={"slug": slug, "display_name": slug.title()})
    assert response.status_code == 201
    return str(response.json()["id"])


ITEMS: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    ("experiences", {"organization": "Org", "title": "Eng"}, {"organization": "Org2", "title": "Lead"}),
    ("achievements", {"title": "Built it"}, {"title": "Built it better"}),
    ("education", {"institution": "Uni"}, {"institution": "College"}),
    ("portfolio", {"name": "Repo"}, {"name": "Repo 2"}),
    ("role-families", {"name": "AI"}, {"name": "ML", "priority": 2}),
    ("role-targets", {"title_pattern": "principal*"}, {"title_pattern": "staff*"}),
]


def create_item(client: TestClient, profile_id: str, path: str, body: dict[str, Any]) -> str:
    response = client.post(f"{API}/{profile_id}/{path}", json=body)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.mark.parametrize(("path", "body", "update"), ITEMS)
def test_item_crud(client: TestClient, path: str, body: dict[str, Any], update: dict[str, Any]) -> None:
    pid = make_profile(client, "owner")
    item_id = create_item(client, pid, path, body)
    assert client.get(f"{API}/{pid}/{path}/{item_id}").status_code == 200
    assert len(client.get(f"{API}/{pid}/{path}").json()) == 1
    changed = client.put(f"{API}/{pid}/{path}/{item_id}", json=update)
    assert changed.status_code == 200
    assert all(changed.json()[k] == v for k, v in update.items())
    assert client.delete(f"{API}/{pid}/{path}/{item_id}").status_code == 204
    assert client.get(f"{API}/{pid}/{path}/{item_id}").status_code == 404


@pytest.mark.parametrize(("path", "body", "update"), ITEMS)
def test_other_profiles_records_are_404_and_unchanged(
    client: TestClient, path: str, body: dict[str, Any], update: dict[str, Any]
) -> None:
    a, b = make_profile(client, "alpha"), make_profile(client, "beta")
    item_id = create_item(client, a, path, body)
    assert client.get(f"{API}/{b}/{path}/{item_id}").status_code == 404
    assert client.put(f"{API}/{b}/{path}/{item_id}", json=update).status_code == 404
    assert client.delete(f"{API}/{b}/{path}/{item_id}").status_code == 404
    assert client.get(f"{API}/{b}/{path}").json() == [] or path in {"experiences", "achievements"}
    original = client.get(f"{API}/{a}/{path}/{item_id}").json()
    assert all(original[k] == v for k, v in body.items())
    assert client.get(f"{API}/missing/{path}/{item_id}").status_code == 404


def test_achievement_cannot_link_another_profiles_experience(client: TestClient) -> None:
    a, b = make_profile(client, "alpha"), make_profile(client, "beta")
    experience = create_item(client, a, "experiences", {"organization": "O", "title": "T"})
    own = create_item(client, b, "achievements", {"title": "mine"})
    response = client.put(
        f"{API}/{b}/achievements/{own}", json={"title": "mine", "experience_id": experience}
    )
    assert response.status_code == 422
    assert client.get(f"{API}/{b}/achievements/{own}").json()["experience_id"] is None


def test_deleting_experience_detaches_achievements(client: TestClient) -> None:
    pid = make_profile(client, "owner")
    experience = create_item(client, pid, "experiences", {"organization": "O", "title": "T"})
    achievement = create_item(
        client, pid, "achievements", {"title": "A", "experience_id": experience}
    )
    client.delete(f"{API}/{pid}/experiences/{experience}")
    assert client.get(f"{API}/{pid}/achievements/{achievement}").json()["experience_id"] is None


def test_preferences_get_and_weight_validation(client: TestClient) -> None:
    pid = make_profile(client, "owner")
    assert client.get(f"{API}/{pid}/search-preferences").json() is None
    assert client.get(f"{API}/{pid}/scoring-preferences").json() is None
    ok = client.put(f"{API}/{pid}/scoring-preferences", json={"weights": {"role_alignment": 0.5}})
    assert ok.status_code == 200
    assert client.get(f"{API}/{pid}/scoring-preferences").json()["weights"] == {"role_alignment": 0.5}
    bad = client.put(f"{API}/{pid}/scoring-preferences", json={"weights": {"charisma": 1}})
    assert bad.status_code == 422
    assert "charisma" in bad.text
    client.put(f"{API}/{pid}/search-preferences", json={"remote_preference": "REQUIRED"})
    assert client.get(f"{API}/{pid}/search-preferences").json()["remote_preference"] == "REQUIRED"
    assert client.get(f"{API}/missing/search-preferences").status_code == 404


def test_skills_and_aliases(client: TestClient) -> None:
    a, b = make_profile(client, "alpha"), make_profile(client, "beta")
    created = client.post(
        f"{API}/{a}/skills", json={"canonical_name": "Python", "aliases": ["Py"], "category": "language"}
    ).json()
    skill_id = created["skill_id"]
    assert created["aliases"] == ["Py"]
    assert [s["canonical_name"] for s in client.get(f"{API}/{a}/skills").json()] == ["Python"]
    assert client.get(f"{API}/{b}/skills").json() == []

    updated = client.put(f"{API}/{a}/skills/{skill_id}", json={"years_experience": 7, "aliases": ["Python3"]})
    assert updated.json()["years_experience"] == 7
    assert updated.json()["aliases"] == ["Py", "Python3"]
    assert client.post(f"{API}/{a}/skills/{skill_id}/aliases", json={"alias": "Pyth"}).json() == [
        "Py", "Pyth", "Python3",
    ]  # fmt: skip

    # Profile B does not hold the skill: every skill endpoint is a 404 and nothing changes.
    assert client.put(f"{API}/{b}/skills/{skill_id}", json={"years_experience": 1}).status_code == 404
    assert client.delete(f"{API}/{b}/skills/{skill_id}").status_code == 404
    assert client.get(f"{API}/{b}/skills/{skill_id}/aliases").status_code == 404
    assert client.post(f"{API}/{b}/skills/{skill_id}/aliases", json={"alias": "x"}).status_code == 404
    assert client.delete(f"{API}/{b}/skills/{skill_id}/aliases/Py").status_code == 404
    assert client.get(f"{API}/{a}/skills/{skill_id}/aliases").json() == ["Py", "Pyth", "Python3"]

    other = client.post(f"{API}/{a}/skills", json={"canonical_name": "Go"}).json()["skill_id"]
    assert client.post(f"{API}/{a}/skills/{other}/aliases", json={"alias": "Py"}).status_code == 409

    assert client.delete(f"{API}/{a}/skills/{skill_id}/aliases/Pyth").status_code == 204
    assert client.delete(f"{API}/{a}/skills/{skill_id}").status_code == 204
    assert [s["canonical_name"] for s in client.get(f"{API}/{a}/skills").json()] == ["Go"]


def test_export_import_round_trips_every_entity_type(client: TestClient) -> None:
    pid = make_profile(client, "full")
    client.put(f"{API}/{pid}/contact", json={"full_name": "Full Person", "city": "Paris"})
    experience = create_item(client, pid, "experiences", {"organization": "Org", "title": "Eng"})
    create_item(client, pid, "achievements", {"title": "Ship", "experience_id": experience, "verified": True})
    create_item(client, pid, "education", {"institution": "Uni"})
    create_item(client, pid, "portfolio", {"name": "Repo", "technologies": ["py"]})
    create_item(client, pid, "role-families", {"name": "AI", "priority": 1})
    create_item(client, pid, "role-targets", {"title_pattern": "principal*", "target_seniority": ["principal"]})
    client.post(f"{API}/{pid}/skills", json={"canonical_name": "Python", "aliases": ["Py"], "years_experience": 5})
    client.put(f"{API}/{pid}/search-preferences", json={"remote_preference": "REQUIRED", "minimum_base_salary": 100})
    client.put(f"{API}/{pid}/scoring-preferences", json={"weights": {"role_alignment": 1.0}})

    exported = client.get(f"{API}/{pid}/export").json()
    assert exported["schema_version"] == 2
    for key in ("experiences", "achievements", "skills", "education", "portfolio", "role_families", "role_targets"):
        assert len(exported[key]) == 1, key
    assert exported["achievements"][0]["experience_index"] == 0

    exported["profile"]["slug"] = "full-copy"
    imported = client.post(f"{API}/import", json=exported)
    assert imported.status_code == 201, imported.text
    new_id = imported.json()["id"]
    again = client.get(f"{API}/{new_id}/export").json()
    exported["profile"]["slug"] = "full-copy"
    assert again == exported
    new_experience = client.get(f"{API}/{new_id}/experiences").json()[0]["id"]
    assert client.get(f"{API}/{new_id}/achievements").json()[0]["experience_id"] == new_experience
    assert new_experience != experience


def test_import_accepts_v1_and_rejects_unknown_versions(client: TestClient) -> None:
    v1 = {"schema_version": 1, "profile": {"slug": "legacy", "display_name": "Legacy"}}
    assert client.post(f"{API}/import", json=v1).status_code == 201
    assert client.post(f"{API}/import", json={**v1, "schema_version": 9}).status_code == 422
    assert client.post(f"{API}/import", json=v1).status_code == 409


def test_import_tolerates_out_of_range_experience_index(client: TestClient) -> None:
    payload = {
        "profile": {"slug": "odd", "display_name": "Odd"},
        "achievements": [{"title": "A", "experience_index": 5}],
    }
    created = client.post(f"{API}/import", json=payload)
    assert created.status_code == 201
    achievements = client.get(f"{API}/{created.json()['id']}/achievements").json()
    assert achievements[0]["experience_id"] is None
    assert client.post(f"{API}/import", json=payload).status_code == 409


def test_seeded_profiles_export_and_import(client: TestClient) -> None:
    engine = client.app.dependency_overrides[get_session]  # type: ignore[attr-defined]
    with next(engine()) as session:
        seed_session(session)
    profiles = client.get(API).json()
    assert len(profiles) == 2
    for profile in profiles:
        exported = client.get(f"{API}/{profile['id']}/export").json()
        assert exported["skills"] and exported["role_families"] and exported["search_preferences"]
        exported["profile"]["slug"] += "-copy"
        assert client.post(f"{API}/import", json=exported).status_code == 201
