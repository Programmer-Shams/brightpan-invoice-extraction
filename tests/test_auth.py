from fastapi.testclient import TestClient

from app import config, db, worker
from app.main import app

client = TestClient(app)  # not entered as a context manager: no lifespan, so no database or worker


def test_health_is_open_and_reports_what_is_down(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    monkeypatch.setenv("RUN_WORKER", "0")
    monkeypatch.setattr(db, "ping", lambda: True)
    assert client.get("/health").status_code == 200
    monkeypatch.setattr(db, "ping", lambda: False)
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["database"] is False
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setenv("RUN_WORKER", "1")
    monkeypatch.setattr(worker, "state", {"threads": [], "last_poll": None})
    assert client.get("/health").status_code == 503                 # worker expected but not running


def test_api_docs_and_schema_are_not_exposed():
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, headers={"Authorization": "Bearer x"}).status_code in (401, 404)


def test_requests_without_the_token_are_rejected(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/review/00000000-0000-0000-0000-000000000001", json={"action": "approve"}).status_code == 401


def test_api_refuses_to_run_open_when_no_token_is_configured(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "")
    assert client.get("/documents", headers={"Authorization": "Bearer "}).status_code == 503


def test_read_again_only_for_failed_documents(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret-token")
    auth = {"Authorization": "Bearer secret-token"}
    doc = "/documents/00000000-0000-0000-0000-000000000001/retry"
    monkeypatch.setattr(db, "requeue_failed", lambda _id: True)
    assert client.post(doc, headers=auth).status_code == 202
    monkeypatch.setattr(db, "requeue_failed", lambda _id: False)        # not failed (or not found)
    assert client.post(doc, headers=auth).status_code == 409
    assert client.post(doc).status_code == 401
