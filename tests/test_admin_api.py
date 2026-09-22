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
    assert '<div id="app"></div>' in res.text


def test_admin_static_assets_serve(client):
    import re
    res = client.get("/admin")
    assert res.status_code == 200
    match = re.search(r'src="(/admin/assets/[^"]+\.js)"', res.text)
    assert match is not None, "JS asset script tag not found in /admin HTML"
    js_url = match.group(1)
    res_js = client.get(js_url)
    assert res_js.status_code == 200
    assert len(res_js.content) > 1000


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

    # Clean up leftover if any
    client.delete("/api/admin/providers/test-provider-unit", headers=auth_headers)

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

    # Clean up
    client.delete("/api/admin/providers/test-provider-unit", headers=auth_headers)


def test_admin_playground_endpoint(client, auth_headers):
    payload = {"text": "ကစားသမား ID မှားနေတယ်"}
    res = client.post("/api/admin/playground", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "ok" in data
    assert data["src_lang"] == "my"
    assert "member" in data["policy_hits"]


def test_admin_policy_endpoint(client, auth_headers):
    res = client.get("/api/admin/policy", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert "concepts" in data
    assert len(data["concepts"]) > 0
    assert "deny_terms" in data
    assert "my" in data["deny_terms"]
    assert "en" in data["deny_terms"]


def test_admin_providers_update_and_delete_in_memory(client, auth_headers):
    # Clean up test item if leftover
    client.delete("/api/admin/providers/test-crud-item", headers=auth_headers)

    # 1. Create a dedicated provider for update/delete test
    setup_payload = {
        "name": "test-crud-item",
        "base_url": "https://crud.example.com/v1",
        "model": "crud-base-model",
        "priority": 9,
        "timeout_s": 10.0,
        "enabled": True,
        "api_key": "sk-crud-123",
    }
    res = client.post("/api/admin/providers", json=setup_payload, headers=auth_headers)
    assert res.status_code == 200

    # 2. Update provider
    update_payload = {
        "name": "test-crud-item",
        "base_url": "https://updated.example.com/v1",
        "model": "test-updated-model",
        "priority": 3,
        "timeout_s": 25.0,
        "enabled": True,
        "api_key": "sk-updated-key",
    }
    res = client.put("/api/admin/providers/test-crud-item", json=update_payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify update reflected
    res = client.get("/api/admin/providers", headers=auth_headers)
    updated_p = next(p for p in res.json()["providers"] if p["name"] == "test-crud-item")
    assert updated_p["base_url"] == "https://updated.example.com/v1"
    assert updated_p["model"] == "test-updated-model"

    # 3. Delete provider
    res = client.delete("/api/admin/providers/test-crud-item", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify deleted
    res = client.get("/api/admin/providers", headers=auth_headers)
    remaining_names = [p["name"] for p in res.json()["providers"]]
    assert "test-crud-item" not in remaining_names


def test_admin_audit_logs_fallback(client, auth_headers):
    res = client.get("/api/admin/logs", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert len(data["logs"]) >= 1
    first_log = data["logs"][0]
    assert "provider" in first_log
    assert "status" in first_log
    assert "latency_ms" in first_log


def test_admin_provider_toggle_and_anthropic_test(client, auth_headers):
    # 1. Create a provider with enabled=False (Paused)
    payload = {
        "name": "claude-test-provider",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-20241022",
        "priority": 10,
        "timeout_s": 20.0,
        "enabled": False,
        "api_key": "sk-ant-test-mock-key",
    }
    res = client.post("/api/admin/providers", json=payload, headers=auth_headers)
    assert res.status_code == 200

    # 2. Check provider exists with breaker_state="paused"
    res = client.get("/api/admin/providers", headers=auth_headers)
    assert res.status_code == 200
    p = next(x for x in res.json()["providers"] if x["name"] == "claude-test-provider")
    assert p["enabled"] is False
    assert p["breaker_state"] == "paused"

    # 3. Toggle enabled to True
    payload["enabled"] = True
    res = client.put("/api/admin/providers/claude-test-provider", json=payload, headers=auth_headers)
    assert res.status_code == 200

    res = client.get("/api/admin/providers", headers=auth_headers)
    p = next(x for x in res.json()["providers"] if x["name"] == "claude-test-provider")
    assert p["enabled"] is True

    # 4. Clean up
    client.delete("/api/admin/providers/claude-test-provider", headers=auth_headers)



