from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_run_validation_error() -> None:
    response = client.post(
        "/api/ad-intel/run",
        json={"ad_type": "", "keywords": [], "platform": "xhs", "limit": 20, "time_range": ""},
    )
    assert response.status_code == 422
