"""Encryption utilities for sensitive credentials stored at rest (Spec §08-16).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with key derivation from config.
Provides backward compatibility for existing unencrypted credentials in the database.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .. import config

log = logging.getLogger("opstranslate.crypto")


def _get_fernet() -> Fernet:
    """Derive a deterministic 32-byte Fernet key from available secret."""
    raw_key = config.get("ENCRYPTION_KEY", "")
    if not raw_key:
        raw_key = (
            config.get("SECRET_KEY", "")
            or config.get("ADMIN_PASSWORD", "")
            or config.get("WEBHOOK_SECRET", "")
            or "opstranslate-default-secret-salt-v1"
        )
    
    # Use SHA256 of the secret as 32-byte key, urlsafe base64 encoded
    key_32 = hashlib.sha256(raw_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_32)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: str) -> bytes | None:
    """Encrypt a plaintext string into Fernet token bytes."""
    if not plaintext:
        return None
    try:
        f = _get_fernet()
        return f.encrypt(plaintext.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("crypto_encrypt_failed: %s", exc)
        # Fallback to UTF-8 bytes if encryption fails
        return plaintext.encode("utf-8")


def decrypt_secret(token: bytes | None) -> str:
    """Decrypt Fernet token bytes into plaintext string.
    
    If token is not valid Fernet or is legacy plaintext UTF-8 bytes,
    gracefully decodes as UTF-8 for backward compatibility.
    """
    if not token:
        return ""
    
    # Check if token is likely a Fernet token (starts with b"gAAAAA")
    if token.startswith(b"gAAAAA"):
        try:
            f = _get_fernet()
            return f.decrypt(token).decode("utf-8")
        except InvalidToken:
            log.warning("crypto_decrypt_invalid_token, attempting utf-8 fallback")
        except Exception as exc:  # noqa: BLE001
            log.warning("crypto_decrypt_error: %s, attempting utf-8 fallback", exc)
    
    # Backward-compatible fallback for pre-existing unencrypted rows
    return token.decode("utf-8", errors="ignore")
