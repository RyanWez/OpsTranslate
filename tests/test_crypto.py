import pytest

from app.store.crypto import decrypt_secret, encrypt_secret
from app.store.models import Provider


def test_encrypt_decrypt_roundtrip():
    key = "sk-test-secret-key-12345"
    encrypted = encrypt_secret(key)
    assert encrypted is not None
    assert encrypted.startswith(b"gAAAAA")
    assert encrypted != key.encode("utf-8")
    
    decrypted = decrypt_secret(encrypted)
    assert decrypted == key


def test_decrypt_legacy_plaintext_utf8():
    legacy_key = "sk-legacy-unencrypted-key"
    legacy_bytes = legacy_key.encode("utf-8")
    
    # Gracefully falls back to plain utf-8
    decrypted = decrypt_secret(legacy_bytes)
    assert decrypted == legacy_key


def test_decrypt_empty_or_none():
    assert decrypt_secret(None) == ""
    assert decrypt_secret(b"") == ""
    assert encrypt_secret("") is None


def test_provider_model_transparent_encryption():
    p = Provider(name="test_ai", model="gpt-4o", base_url="https://api.openai.com/v1")
    p.api_key = "sk-live-12345678"
    
    # api_key_enc should be encrypted bytes
    assert p.api_key_enc is not None
    assert p.api_key_enc.startswith(b"gAAAAA")
    
    # api_key property returns the decrypted plaintext
    assert p.api_key == "sk-live-12345678"
    
    # Legacy simulated bytea assignment
    p.api_key_enc = b"sk-legacy-plain"
    assert p.api_key == "sk-legacy-plain"
