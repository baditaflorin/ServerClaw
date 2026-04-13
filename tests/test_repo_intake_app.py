from fastapi.testclient import TestClient

from scripts.repo_intake.app import create_app


def test_create_app_health_endpoint_works_without_static_dir() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
