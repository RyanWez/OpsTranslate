"""Encryption utilities for sensitive credentials stored at rest (Spec §08-16).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with the key derived from an explicit
ENCRYPTION_KEY. The key is deliberately NOT derived from ADMIN_PASSWORD or any
other reused secret: a derivable/default key means provider API keys are only
obfuscated, not private, and it couples key rotation to unrelated changes.
Fail-closed - with no ENCRYPTION_KEY, encryption refuses to run rather than
silently writing plaintext.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .. import config

log = logging.getLogger("opstranslate.crypto")


class EncryptionNotConfigured(RuntimeError):
    """Raised when a credential must be encrypted but ENCRYPTION_KEY is unset."""


def is_encryption_configured() -> bool:
    """True only when an explicit ENCRYPTION_KEY is set."""
    return bool(config.get("ENCRYPTION_KEY", ""))


def _get_fernet() -> Fernet:
    """Derive a deterministic 32-byte Fernet key from ENCRYPTION_KEY."""
    raw_key = config.get("ENCRYPTION_KEY", "")
    if not raw_key:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY is not set. Refusing to (de)crypt provider "
            "credentials with a derivable default key. Set a strong "
            "ENCRYPTION_KEY (see .env.example) and re-enter provider API keys."
        )

    # Use SHA256 of the secret as 32-byte key, urlsafe base64 encoded
    key_32 = hashlib.sha256(raw_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_32)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: str) -> bytes | None:
    """Encrypt a plaintext string into Fernet token bytes.

    No silent plaintext fallback: if encryption cannot run (no ENCRYPTION_KEY),
    this raises so a secret is never persisted to the DB in the clear.
    """
    if not plaintext:
        return None
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_secret(token: bytes | None) -> str:
    """Decrypt Fernet token bytes into a plaintext string.

    Legacy plaintext UTF-8 rows (pre-encryption) are decoded as-is for
    backward compatibility. A Fernet token that cannot be decrypted (wrong or
    missing key) returns "" rather than leaking ciphertext bytes as a bogus key.
    """
    if not token:
        return ""

    # Check if token is likely a Fernet token (starts with b"gAAAAA")
    if token.startswith(b"gAAAAA"):
        try:
            f = _get_fernet()
            return f.decrypt(token).decode("utf-8")
        except InvalidToken:
            log.warning("crypto_decrypt_invalid_token (wrong ENCRYPTION_KEY?)")
            return ""
        except EncryptionNotConfigured:
            log.error("crypto_decrypt_skipped: ENCRYPTION_KEY not set")
            return ""
        except Exception as exc:  # noqa: BLE001
            log.warning("crypto_decrypt_error: %s", exc)
            return ""

    # Backward-compatible fallback for pre-existing unencrypted rows
    return token.decode("utf-8", errors="ignore")
