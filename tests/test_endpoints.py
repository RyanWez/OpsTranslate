from fastapi.testclient import TestClient

from app.main import app


def test_root_endpoint():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "OpsTranslate" in data["app"]


def test_healthz_endpoint():
    with TestClient(app) as client:
        res = client.get("/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["policy"] is True


def test_livez_endpoint():
    with TestClient(app) as client:
        res = client.get("/livez")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


def test_webhook_security_gate(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "WEBHOOK_PATH_SECRET", "test_path_123")
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "test_sec_456")

    with TestClient(app) as client:
        # 1. Invalid path secret -> 403
        res = client.post("/webhook/wrong_path", json={"update_id": 1})
        assert res.status_code == 403

        # 2. Valid path but missing/wrong secret header -> 403
        res = client.post("/webhook/test_path_123", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"})
        assert res.status_code == 403

        # 3. Valid path and header -> 200 OK
        res = client.post(
            "/webhook/test_path_123",
            json={"update_id": 1, "message": {"message_id": 10, "date": 1600000000, "chat": {"id": 123, "type": "private"}}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test_sec_456"},
        )
        assert res.status_code == 200
        assert res.json() == {"ok": True}
