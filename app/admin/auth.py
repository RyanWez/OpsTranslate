"""Admin authentication and session management."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, status

from .. import config

_SALT = "opstranslate-admin-salt-v1"


def get_expected_token() -> str:
    pwd = config.get("ADMIN_PASSWORD", "admin123")
    return hashlib.sha256(f"{pwd}:{_SALT}".encode()).hexdigest()


def verify_password(password: str) -> bool:
    expected = config.get("ADMIN_PASSWORD", "admin123")
    return hmac.compare_digest(password.strip(), expected.strip())


def is_authenticated(request: Request) -> bool:
    expected = get_expected_token()
    # Check cookie
    cookie_token = request.cookies.get("admin_session")
    if cookie_token and isinstance(cookie_token, str) and hmac.compare_digest(cookie_token, expected):
        return True
    # Check header: Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and isinstance(auth_header, str):
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            if hmac.compare_digest(parts[1], expected):
                return True
    return False


async def require_admin(request: Request) -> bool:
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
