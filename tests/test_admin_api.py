"""Tests for Admin Panel endpoints and authentication."""
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


def test_admin_page_serves_html(client):
    res = client.get("/admin")
    assert res.status_code == 200
    assert "OpsTranslate Control Center" in res.text
    assert "admin.css" in res.text
    assert "admin.js" in res.text


def test_admin_static_assets_serve(client):
    res_css = client.get("/admin-static/admin.css")
    assert res_css.status_code == 200
    assert "--bg-canvas" in res_css.text

    res_js = client.get("/admin-static/admin.js")
    assert res_js.status_code == 200
    assert "OpsTranslate Control Center" in res_js.text


def test_admin_auth_flow(client, monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": "mypass123" if k == "ADMIN_PASSWORD" else default)

    # 1. Unauthenticated request fails
    res = client.get("/api/admin/overview")
    assert res.status_code == 401

    # 2. Bad password fails
    res = client.post("/api/admin/login", json={"password": "wrongpassword"})
    assert res.status_code == 401

    # 3. Correct password succeeds and sets session
    res = client.post("/api/admin/login", json={"password": "mypass123"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "token" in data
    token = data["token"]

    # 4. Bearer token works
    res = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "active_provider_count" in data


def test_admin_providers_endpoints(client, auth_headers):
    # List providers
    res = client.get("/api/admin/providers", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert len(data["providers"]) >= 1

    # Create new provider
    payload = {
        "name": "test-provider-unit",
        "base_url": "https://api.example.com/v1",
        "model": "gpt-4o-mini",
        "priority": 5,
        "timeout_s": 12.0,
        "enabled": True,
        "api_key": "sk-unit-test-1234",
    }
    res = client.post("/api/admin/providers", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify provider was reloaded in memory router
    res = client.get("/api/admin/providers", headers=auth_headers)
    names = [p["name"] for p in res.json()["providers"]]
    assert "test-provider-unit" in names


def test_admin_playground_endpoint(client, auth_headers):
    payload = {"text": "ကစားသမား ID မှားနေတယ်"}
    res = client.post("/api/admin/playground", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["src_lang"] == "my"
    assert "member" in data["policy_hits"]
    assert "final_output" in data
