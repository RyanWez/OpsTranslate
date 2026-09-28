"""Fail-closed security behaviors: admin auth, credential encryption,
brute-force IP bucketing, and constant-time webhook checks."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.admin import auth
from app.store import crypto


# --- Admin password fail-closed --------------------------------------------

@pytest.mark.parametrize("value", ["", "admin123"])
def test_admin_login_disabled_without_strong_password(monkeypatch, value):
    monkeypatch.setattr(config, "get", lambda k, default="": value if k == "ADMIN_PASSWORD" else default)
    assert auth.is_admin_password_configured() is False
    # Even the "correct" default is rejected.
    assert auth.verify_password(value) is False
    # A session token signed under this config must not validate.
    token = auth.create_session_token(duration_s=3600)
    assert auth.validate_token(token) is False


def test_admin_login_works_with_strong_password(monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": "a-strong-secret" if k == "ADMIN_PASSWORD" else default)
    assert auth.is_admin_password_configured() is True
    assert auth.verify_password("a-strong-secret") is True
    assert auth.verify_password("wrong") is False
    assert auth.validate_token(auth.create_session_token(duration_s=3600)) is True


def test_login_endpoint_rejects_default_password(monkeypatch):
    from app.admin.auth import _login_failures

    _login_failures.clear()
    # Unconfigured: falls back to the old default in code, must still 401.
    monkeypatch.setattr(config, "get", lambda k, default="": default)
    with TestClient(app_module().app) as client:
        res = client.post("/api/admin/login", json={"password": "admin123"})
        assert res.status_code == 401
    _login_failures.clear()


# --- Encryption fail-closed ------------------------------------------------

def test_encrypt_raises_without_key(monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": default)
    assert crypto.is_encryption_configured() is False
    with pytest.raises(crypto.EncryptionNotConfigured):
        crypto.encrypt_secret("sk-should-not-persist")


def test_encrypt_no_plaintext_fallback(monkeypatch):
    """A failed encryption must never return the plaintext bytes."""
    monkeypatch.setattr(config, "get", lambda k, default="": default)
    try:
        out = crypto.encrypt_secret("sk-secret")
    except crypto.EncryptionNotConfigured:
        out = None
    assert out != b"sk-secret"


def test_decrypt_wrong_key_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": "key-A" if k == "ENCRYPTION_KEY" else default)
    token = crypto.encrypt_secret("sk-live-1234")
    assert token is not None
    # Rotate the key: the old token can no longer be decrypted, and we get ""
    # rather than leaked ciphertext bytes decoded as a bogus key.
    monkeypatch.setattr(config, "get", lambda k, default="": "key-B" if k == "ENCRYPTION_KEY" else default)
    assert crypto.decrypt_secret(token) == ""


# --- Brute-force IP bucketing ----------------------------------------------

def test_client_ip_ignores_spoofed_forwarded_for(monkeypatch):
    monkeypatch.setattr(config, "get", lambda k, default="": default)  # no trusted header

    class _Req:
        headers = {"x-forwarded-for": "1.2.3.4", "cf-connecting-ip": "5.6.7.8"}

        class client:
            host = "10.0.0.1"

    ip = auth._get_client_ip(_Req())
    assert ip == "10.0.0.1"  # socket peer, not the attacker-supplied header


def test_client_ip_trusts_configured_header(monkeypatch):
    monkeypatch.setattr(
        config, "get", lambda k, default="": "Fly-Client-IP" if k == "TRUSTED_CLIENT_IP_HEADER" else default
    )

    class _Req:
        headers = {"fly-client-ip": "9.9.9.9", "x-forwarded-for": "1.2.3.4"}

        class client:
            host = "10.0.0.1"

    assert auth._get_client_ip(_Req()) == "9.9.9.9"


def app_module():
    import app.main as m

    return m
