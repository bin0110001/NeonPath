from fastapi.testclient import TestClient

from careerflow.main import create_app


def test_liveness_is_available_without_database() -> None:
    response = TestClient(create_app()).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
