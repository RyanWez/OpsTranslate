import pytest
from unittest.mock import AsyncMock, MagicMock
from app.store.userstore import UserStore
from app.store.models import AllowedUser


@pytest.mark.asyncio
async def test_user_store_sync_in_memory():
    store = UserStore()
    assert hasattr(store, "_discovered_users")

    # Sync profile without db configured
    await store.sync_user_profile(
        user_id=12345678,
        full_name="Daw Khin",
        username="daw_khin",
        auto_allow=True,
    )

    discovered = store.get_discovered_users()
    matched = [u for u in discovered if u["user_id"] == 12345678]
    assert len(matched) == 1
    u = matched[0]
    assert u["display_name"] == "Daw Khin"
    assert u["username"] == "daw_khin"
    assert u["active"] is True
    assert u["last_active_at"] is not None

    # Sync again with updated name and inactive
    await store.sync_user_profile(
        user_id=12345678,
        full_name="Daw Khin (Updated)",
        username="@daw_khin_new",
        auto_allow=False,
    )
    discovered_updated = store.get_discovered_users()
    u2 = [u for u in discovered_updated if u["user_id"] == 12345678][0]
    assert u2["display_name"] == "Daw Khin (Updated)"
    assert u2["username"] == "daw_khin_new"
    # Existing active status is preserved
    assert u2["active"] is True


@pytest.mark.asyncio
async def test_api_user_routes_with_discovered(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.admin import auth

    # Mock admin authentication
    monkeypatch.setattr(auth, "is_authenticated", lambda req: True)

    with TestClient(app) as client:
        # Pre-populate discovered user in services.user_store
        services = app.state.services
        await services.user_store.sync_user_profile(
            user_id=999888,
            full_name="Ko Aung",
            username="koaung",
            auto_allow=True,
        )

        # GET /api/admin/users
        res = client.get("/api/admin/users")
        assert res.status_code == 200
        data = res.json()
        users = data.get("users", [])
        matched = [u for u in users if u["user_id"] == 999888]
        assert len(matched) == 1
        user = matched[0]
        assert user["display_name"] == "Ko Aung"
        assert user["username"] == "koaung"
        assert user["active"] is True

        # PATCH /api/admin/users/999888/status
        toggle_res = client.patch("/api/admin/users/999888/status", json={"active": False})
        assert toggle_res.status_code == 200
        assert toggle_res.json()["active"] is False

        # Verify status toggled
        res_after = client.get("/api/admin/users")
        matched_after = [u for u in res_after.json()["users"] if u["user_id"] == 999888]
        assert matched_after[0]["active"] is False
