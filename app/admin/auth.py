"""Admin authentication and session management with timed tokens and brute-force protection."""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, status

from .. import config

_SALT = "opstranslate-admin-salt-v1"
SESSION_DURATION_S = 86400 * 7  # 7 days

# IP -> deque of failure timestamps (sliding 5-minute window)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_S = 300.0


def _get_secret_key() -> bytes:
    pwd = config.get("ADMIN_PASSWORD", "admin123")
    return f"{pwd}:{_SALT}".encode()


def create_session_token(duration_s: int = SESSION_DURATION_S) -> str:
    """Generate a timed HMAC-signed admin session token."""
    expiry = int(time.time() + duration_s)
    secret = _get_secret_key()
    signature = hmac.new(secret, f"{expiry}".encode(), hashlib.sha256).hexdigest()
    return f"v1:{expiry}:{signature}"


def get_expected_token() -> str:
    """Legacy helper returning a fresh valid session token."""
    return create_session_token()


def verify_password(password: str) -> bool:
    expected = config.get("ADMIN_PASSWORD", "admin123")
    return hmac.compare_digest(password.strip(), expected.strip())


def validate_token(token: str | None) -> bool:
    """Validate a session token: checks signature and expiration."""
    if not token or not isinstance(token, str):
        return False
    token = token.strip()

    # 1. Timed v1 token format: v1:{expiry}:{signature}
    if token.startswith("v1:"):
        parts = token.split(":")
        if len(parts) == 3:
            _, expiry_str, sig = parts
            try:
                expiry = int(expiry_str)
                if time.time() > expiry:
                    return False  # Expired
                secret = _get_secret_key()
                expected_sig = hmac.new(secret, expiry_str.encode(), hashlib.sha256).hexdigest()
                return hmac.compare_digest(sig, expected_sig)
            except (ValueError, TypeError):
                return False

    # 2. Backward compatibility with static token (legacy)
    legacy = hashlib.sha256(_get_secret_key()).hexdigest()
    return hmac.compare_digest(token, legacy)


def _get_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(request: Request) -> None:
    """Check sliding window failed attempts per client IP."""
    client_ip = _get_client_ip(request)
    now = time.time()
    q = _login_failures[client_ip]
    while q and (now - q[0] > LOCKOUT_WINDOW_S):
        q.popleft()
    if len(q) >= MAX_LOGIN_ATTEMPTS:
        retry_after = int(LOCKOUT_WINDOW_S - (now - q[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please wait {max(retry_after, 1)} seconds.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def record_login_failure(request: Request) -> None:
    client_ip = _get_client_ip(request)
    _login_failures[client_ip].append(time.time())


def record_login_success(request: Request) -> None:
    client_ip = _get_client_ip(request)
    _login_failures.pop(client_ip, None)


def is_authenticated(request: Request) -> bool:
    # Check cookie
    cookie_token = request.cookies.get("admin_session")
    if cookie_token and validate_token(cookie_token):
        return True
    # Check header: Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and isinstance(auth_header, str):
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            if validate_token(parts[1]):
                return True
    # Check query param (fallback for SSE)
    query_token = request.query_params.get("token")
    if query_token and validate_token(query_token):
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

