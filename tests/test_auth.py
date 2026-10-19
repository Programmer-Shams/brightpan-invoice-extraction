from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)  # not entered as a context manager: no lifespan, so no database or worker


def test_health_is_open(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    assert client.get("/health").status_code == 200


def test_requests_without_the_token_are_rejected(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/review/00000000-0000-0000-0000-000000000001", json={"action": "approve"}).status_code == 401


def test_api_refuses_to_run_open_when_no_token_is_configured(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "")
    assert client.get("/documents", headers={"Authorization": "Bearer "}).status_code == 503
