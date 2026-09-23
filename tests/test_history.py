import pytest
from fastapi.testclient import TestClient

from app import config
from app.admin.auth import get_expected_token
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": "secret-pass" if k == "ADMIN_PASSWORD" else default)
    token = get_expected_token()
    return {"Authorization": f"Bearer {token}"}


def test_translation_history_api_endpoints(client, auth_headers):
    # 1. Query history list
    res = client.get("/api/admin/history?page=1&page_size=20", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data

    # 2. Search query returns 200
    search_res = client.get("/api/admin/history?search=nonexistent_token_123456", headers=auth_headers)
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 0

    # 3. Prune endpoint
    prune_res = client.delete("/api/admin/history/prune?days=365", headers=auth_headers)
    assert prune_res.status_code == 200
    assert prune_res.json()["ok"] is True
