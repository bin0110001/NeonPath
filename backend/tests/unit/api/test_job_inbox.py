from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.jobs import get_session
from careerflow.api.profiles import get_session as get_profile_session
from careerflow.infrastructure.database.models import Base, ProfileModel
from careerflow.main import create_app
from careerflow.seed import seed_session

JOBS = "/api/v1/jobs"


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
    app.dependency_overrides[get_profile_session] = override
    with Session(engine) as session:
        seed_session(session)
    return TestClient(app)


def profile_ids(client: TestClient) -> dict[str, str]:
    return {p["slug"]: p["id"] for p in client.get("/api/v1/profiles").json()}


@pytest.fixture
def ids(client: TestClient) -> dict[str, str]:
    ids = profile_ids(client)
    # Evaluate every seeded job for every profile via the API.
    for job in client.get(JOBS, params={"profile_id": ids["jordan-lee"]}).json():
        assert client.post(f"{JOBS}/{job['id']}/evaluate-all").status_code == 201
    return ids


def companies(client: TestClient, profile: str, **params: object) -> list[str]:
    response = client.get(JOBS, params={"profile_id": profile, **params})
    assert response.status_code == 200, response.text
    return [j["company"] for j in response.json()]


def test_profile_id_is_required_and_validated(client: TestClient) -> None:
    assert client.get(JOBS).status_code == 422
    assert client.get(JOBS, params={"profile_id": "nope"}).status_code == 404
    assert client.get(f"{JOBS}/dashboard", params={"profile_id": "nope"}).status_code == 404


def test_items_carry_profile_scoped_status_and_score(client: TestClient, ids: dict[str, str]) -> None:
    jordan, morgan = ids["jordan-lee"], ids["morgan-rivera"]
    by_company = {
        j["company"]: j for j in client.get(JOBS, params={"profile_id": jordan}).json()
    }
    lumen = by_company["Lumen Robotics"]
    assert lumen["workflow_status"] == "READY_FOR_REVIEW"
    assert lumen["score"] is not None and lumen["score"] > 0.7
    assert by_company["Smokestack Tobacco"]["has_blockers"] is True

    client.post(f"{JOBS}/{lumen['id']}/shortlist", json={"profile_id": jordan})
    assert companies(client, jordan, status="SHORTLISTED") == ["Lumen Robotics"]
    assert companies(client, morgan, status="SHORTLISTED") == []  # other profile unaffected


def test_filters_apply_on_the_server(client: TestClient, ids: dict[str, str]) -> None:
    jordan, morgan = ids["jordan-lee"], ids["morgan-rivera"]
    assert companies(client, jordan, min_score=0.7) == ["Lumen Robotics"]
    assert set(companies(client, morgan, min_score=0.7)) >= {"Harbor Retail Group"}
    assert "Lumen Robotics" not in companies(client, morgan, min_score=0.7)
    assert set(companies(client, jordan, remote_type="REMOTE")) == {"Lumen Robotics", "Blue Meridian Health"}
    assert companies(client, jordan, location="chicago") == ["Harbor Retail Group"]
    assert companies(client, jordan, company="smoke") == ["Smokestack Tobacco"]
    # Jordan requires remote and $170k+: Harbor is hybrid, Blue Meridian pays less, Smokestack is excluded.
    assert set(companies(client, jordan, has_blockers="true")) == {
        "Harbor Retail Group", "Blue Meridian Health", "Smokestack Tobacco",
    }  # fmt: skip
    assert companies(client, jordan, has_blockers="false") == ["Lumen Robotics"]
    assert companies(client, jordan, q="tableau") == ["Harbor Retail Group"]
    assert companies(client, jordan, source="rss") == []
    assert companies(client, jordan, posted_after="2999-01-01T00:00:00Z") == []
    assert client.get(JOBS, params={"profile_id": jordan, "min_score": 2}).status_code == 422


def test_source_filter(client: TestClient, ids: dict[str, str]) -> None:
    jordan = ids["jordan-lee"]
    job = client.get(JOBS, params={"profile_id": jordan}).json()[0]
    client.post(f"{JOBS}/{job['id']}/sources", json={"adapter": "rss", "raw_payload": {}})
    assert companies(client, jordan, source="rss") == [job["company"]]


def test_sorting_and_pagination(client: TestClient, ids: dict[str, str]) -> None:
    jordan = ids["jordan-lee"]
    everything = companies(client, jordan, sort="score")
    assert everything[0] == "Lumen Robotics"
    assert companies(client, jordan, sort="score", descending="false")[-1] == "Lumen Robotics"
    first = client.get(JOBS, params={"profile_id": jordan, "sort": "title", "limit": 2, "offset": 0})
    second = client.get(JOBS, params={"profile_id": jordan, "sort": "title", "limit": 2, "offset": 2})
    assert first.headers["X-Total-Count"] == second.headers["X-Total-Count"] == "4"
    paged = [j["id"] for j in first.json() + second.json()]
    assert len(set(paged)) == 4
    titles = [j["title"] for j in first.json() + second.json()]
    assert titles == sorted(titles, reverse=True)
    assert client.get(JOBS, params={"profile_id": jordan, "limit": 0}).status_code == 422
    assert client.get(JOBS, params={"profile_id": jordan, "offset": 99}).json() == []


def test_unevaluated_jobs_sort_last_and_have_no_score(client: TestClient) -> None:
    jordan = profile_ids(client)["jordan-lee"]
    created = client.post(
        JOBS, json={"title": "Fresh", "company": "Newco", "description_text": "not evaluated yet"}
    )
    assert created.status_code == 201  # plain create does not auto-evaluate (import does)
    items = client.get(JOBS, params={"profile_id": jordan, "sort": "score"}).json()
    assert items[-1]["company"] == "Newco"
    assert items[-1]["score"] is None and items[-1]["has_blockers"] is None
    assert all(j["score"] is not None for j in items[:-1])
    ascending = client.get(JOBS, params={"profile_id": jordan, "sort": "score", "descending": "false"}).json()
    assert ascending[-1]["company"] == "Newco"  # missing scores sort last either way
    assert "Newco" not in companies(client, jordan, min_score=0)
    summary = client.get(f"{JOBS}/dashboard", params={"profile_id": jordan}).json()
    assert summary["unevaluated"] == 1


def test_dashboard_matches_the_list_api(client: TestClient, ids: dict[str, str]) -> None:
    jordan, morgan = ids["jordan-lee"], ids["morgan-rivera"]
    lumen = next(
        j for j in client.get(JOBS, params={"profile_id": jordan}).json() if j["company"] == "Lumen Robotics"
    )
    client.post(f"{JOBS}/{lumen['id']}/shortlist", json={"profile_id": jordan})

    for profile in (jordan, morgan):
        summary = client.get(f"{JOBS}/dashboard", params={"profile_id": profile}).json()
        items = client.get(JOBS, params={"profile_id": profile}).json()
        assert summary["total"] == len(items) == 4
        assert summary["needs_review"] == len(companies(client, profile, status="READY_FOR_REVIEW"))
        assert summary["shortlisted"] == len(companies(client, profile, status="SHORTLISTED"))
        assert summary["blocked"] == len(companies(client, profile, has_blockers="true"))
        assert summary["high_fit"] == len(
            [j for j in items if j["score"] >= 0.7 and not j["has_blockers"]]
        )
        assert sum(summary["by_status"].values()) == summary["total"]
        assert summary["new_jobs"] == summary["needs_review"]  # all seeded just now

    assert client.get(f"{JOBS}/dashboard", params={"profile_id": jordan}).json()["shortlisted"] == 1
    assert client.get(f"{JOBS}/dashboard", params={"profile_id": morgan}).json()["shortlisted"] == 0
    assert client.get(f"{JOBS}/dashboard", params={"profile_id": jordan, "remote_type": "ONSITE"}).json()["total"] == 1


def test_profiles_exist_in_fixture(client: TestClient) -> None:
    assert len(profile_ids(client)) == 2
    assert ProfileModel.__tablename__ == "profiles"
