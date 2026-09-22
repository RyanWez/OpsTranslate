"""Admin API router for OpsTranslate Bot."""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from .. import config
from ..policy.policy import (
    PLACEHOLDER_RE,
    _dominant_script,
    build_system_prompt,
    deny_scan,
    mask,
    protect_entities,
    render,
    restore_entities,
    sanitize_leaks,
)
from ..services.pipeline import Services, resolve_toggle_dst
from ..services.provider import Provider as ServiceProvider
from ..store import db as dbmod
from ..store.models import AllowedUser, Provider as DBProvider, UsageLog
from ..store.providers import (
    get_active_service_providers,
    load_stored_providers,
    save_stored_providers,
    sync_router_providers,
)
from fastapi.responses import StreamingResponse
from .sse import broadcaster, sse_event_stream
from .auth import (
    check_login_rate_limit,
    create_session_token,
    get_expected_token,
    is_authenticated,
    record_login_failure,
    record_login_success,
    require_admin,
    verify_password,
)

from zoneinfo import ZoneInfo

YANGON = ZoneInfo("Asia/Yangon")


def to_mmt_str(dt: datetime.datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(YANGON).strftime(fmt)


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---- SSE Real-time Stream -------------------------------------------------

@router.get("/events", dependencies=[Depends(require_admin)])
async def sse_events(request: Request):
    """Server-Sent Events (SSE) stream for real-time dashboard state synchronization."""
    if broadcaster._closing:
        raise HTTPException(status_code=503, detail="Server is shutting down")
    q = broadcaster.subscribe()
    return StreamingResponse(
        sse_event_stream(q, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Request / Response Models --------------------------------------------

class LoginRequest(BaseModel):
    password: str


class ProviderPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    base_url: str = Field(..., min_length=1)
    api_key: Optional[str] = None
    model: str = Field(..., min_length=1, max_length=128)
    priority: int = Field(default=1, ge=1, le=100)
    enabled: bool = True
    timeout_s: float = Field(default=15.0, ge=1.0, le=120.0)


class TestProviderRequest(BaseModel):
    id: Optional[Any] = None
    base_url: str
    api_key: Optional[str] = ""
    model: str
    timeout_s: float = 15.0



class UserPayload(BaseModel):
    user_id: int
    display_name: Optional[str] = None
    username: Optional[str] = None
    role: str = "staff"  # staff | admin
    daily_soft_cap: int = 200
    active: bool = True


class UserStatusPayload(BaseModel):
    active: bool


class PlaygroundRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    dst: Optional[str] = None


# ---- Auth Endpoints -------------------------------------------------------

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    check_login_rate_limit(request)
    if not verify_password(req.password):
        record_login_failure(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin password.",
        )
    record_login_success(request)
    token = create_session_token()
    is_https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="none" if is_https else "lax",
        secure=is_https,
        max_age=86400 * 7,  # 7 days
    )
    return {"ok": True, "token": token}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("admin_session")
    return {"ok": True}


@router.get("/me")
async def get_me(request: Request):
    auth = is_authenticated(request)
    token = get_expected_token() if auth else None
    return {
        "authenticated": auth,
        "token": token,
        "app": "OpsTranslate Control Center",
        "mode": config.MODE,
    }


# ---- Overview & Health ----------------------------------------------------

@router.get("/overview", dependencies=[Depends(require_admin)])
async def get_overview(request: Request):
    services: Services = request.app.state.services
    breakers = services.router.states()
    
    # DB & Cache checks
    db_ok = await dbmod.ping() if dbmod.is_configured() else False
    cache_ok = await services.cache.ping() if config.REDIS_URL else True

    # Usage stats
    today_spend = 0.0
    try:
        from ..services.pipeline import _today_key
        today_spend = await services.cache.get_float(_today_key("spend"))
    except Exception:
        pass

    telemetry = services.stats.get_telemetry()

    return {
        "status": "ok",
        "mode": config.MODE,
        "auto_toggle": config.AUTO_TOGGLE,
        "max_input_chars": config.MAX_INPUT_CHARS,
        "policy_version": config.POLICY_VERSION,
        "database_configured": dbmod.is_configured(),
        "database_online": db_ok,
        "redis_configured": bool(config.REDIS_URL),
        "redis_online": cache_ok,
        "circuit_states": breakers,
        "active_provider_count": len(services.router.providers),
        "today_spend_usd": round(today_spend, 4),
        "server_time": datetime.datetime.now(YANGON).strftime("%Y-%m-%d %H:%M:%S"),
        "telemetry": telemetry,
    }


# ---- Policy & Term Glossary -----------------------------------------------

class DenyTermPayload(BaseModel):
    lang: str
    term: str


@router.get("/policy", dependencies=[Depends(require_admin)])
async def get_policy(request: Request):
    services: Services = request.app.state.services
    from ..policy.policy_data import CONCEPTS
    concepts_out = []
    for c in CONCEPTS:
        concepts_out.append({
            "key": c.key,
            "approved": c.approved,
            "enabled": c.enabled,
            "variants_my": c.variants.get("my", []),
            "variants_en": c.variants.get("en", []),
            "variants_zh": c.variants.get("zh", []),
            "outputs": c.outputs,
        })
    return {
        "version": services.policy.version,
        "concepts": concepts_out,
        "deny_terms": services.policy.deny,
    }


@router.post("/policy/test-regression", dependencies=[Depends(require_admin)])
async def test_policy_regression(request: Request):
    """Run the 40-case regression set and return detailed diagnostics."""
    services: Services = request.app.state.services
    from ..policy.regression_set import REGRESSION_SET, run_all
    results = run_all(services.policy)
    failed_cases = {k: v for k, v in results.items() if v}
    total = len(REGRESSION_SET)
    passed = total - len(failed_cases)
    return {
        "ok": len(failed_cases) == 0,
        "total": total,
        "passed": passed,
        "failed": len(failed_cases),
        "results": results,
    }


@router.post("/policy/deny-terms", dependencies=[Depends(require_admin)])
async def add_deny_term(payload: DenyTermPayload, request: Request):
    """Add a custom forbidden output term, guarded by regression test verification."""
    lang = payload.lang.lower().strip()
    term = payload.term.strip()
    if lang not in ("en", "my", "zh"):
        raise HTTPException(status_code=400, detail="Invalid language. Supported: en, my, zh")
    if not term:
        raise HTTPException(status_code=400, detail="Term cannot be empty")

    services: Services = request.app.state.services
    current_deny = services.policy.deny.setdefault(lang, [])
    if term in current_deny:
        return {"ok": True, "term": term, "lang": lang, "message": "Term already present"}

    # Add and verify against regression test suite
    current_deny.append(term)
    from ..policy.regression_set import REGRESSION_SET, evaluate, run_all
    failures = run_all(services.policy)
    conflicts = [k for k, v in failures.items() if v]

    # Verify that approved cross-script outputs in REGRESSION_SET are not withheld by this deny term
    checked = [c for c in REGRESSION_SET if c.dst == lang and c.src != lang]
    for case in checked:
        rendered = evaluate(case, services.policy)
        hits = deny_scan(rendered, case.dst, services.policy)
        if hits:
            conflicts.append(f"{case.id} (forbidden hit on rendered output: {hits})")

    if conflicts:
        # Conflict detected! Revert addition
        current_deny.remove(term)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add forbidden term '{term}': conflicts with regression case(s): {', '.join(conflicts[:3])}",
        )

    # Persist in DB if configured
    if dbmod.is_configured():
        from ..store.models import DenyTerm
        try:
            async with dbmod.session() as s:
                dt = DenyTerm(
                    policy_version=services.policy.version,
                    lang=lang,
                    term=term,
                )
                s.add(dt)
                await s.commit()
        except Exception as exc:  # noqa: BLE001
            pass

    return {"ok": True, "term": term, "lang": lang, "message": "Forbidden term added and regression verified"}


@router.delete("/policy/deny-terms", dependencies=[Depends(require_admin)])
async def delete_deny_term(lang: str, term: str, request: Request):
    """Remove a custom forbidden output term."""
    lang = lang.lower().strip()
    term = term.strip()
    services: Services = request.app.state.services
    current_deny = services.policy.deny.get(lang, [])
    if term in current_deny:
        current_deny.remove(term)

    if dbmod.is_configured():
        from sqlalchemy import delete
        from ..store.models import DenyTerm
        try:
            async with dbmod.session() as s:
                await s.execute(
                    delete(DenyTerm).where(
                        DenyTerm.policy_version == services.policy.version,
                        DenyTerm.lang == lang,
                        DenyTerm.term == term,
                    )
                )
                await s.commit()
        except Exception as exc:  # noqa: BLE001
            pass

    return {"ok": True, "term": term, "lang": lang}


# ---- Provider Management --------------------------------------------------

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}••••••••{key[-4:]}"


@router.get("/providers", dependencies=[Depends(require_admin)])
async def list_providers(request: Request):
    services: Services = request.app.state.services
    breaker_states = services.router.states()
    out = []

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                result = await sess.execute(select(DBProvider).order_by(DBProvider.priority.asc(), DBProvider.id.asc()))
                rows = result.scalars().all()
                for row in rows:
                    out.append({
                        "id": row.id,
                        "name": row.name,
                        "base_url": row.base_url,
                        "api_key_masked": _mask_key(row.api_key),
                        "model": row.model,
                        "priority": row.priority,
                        "enabled": row.enabled,
                        "timeout_s": float(row.timeout_ms / 1000.0) if row.timeout_ms else 15.0,
                        "breaker_state": breaker_states.get(row.name, "unknown"),
                        "source": "database",
                    })
                if out:
                    return {"providers": out}
        except Exception:
            pass

    # Persistent local storage (data/providers.json)
    stored = load_stored_providers()
    for d in stored:
        b_state = breaker_states.get(d["name"], "closed" if d.get("enabled", True) else "paused")
        out.append({
            "id": d["id"],
            "name": d["name"],
            "base_url": d["base_url"],
            "api_key_masked": _mask_key(d.get("api_key", "")),
            "model": d["model"],
            "priority": d.get("priority", 1),
            "enabled": d.get("enabled", True),
            "timeout_s": d.get("timeout_s", 15.0),
            "breaker_state": b_state,
            "source": "persisted",
        })
    return {"providers": out}


@router.post("/providers", dependencies=[Depends(require_admin)])
async def create_provider(payload: ProviderPayload, request: Request):
    services: Services = request.app.state.services
    new_provider_id = None

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                # Check unique name
                existing = (await sess.execute(select(DBProvider).where(DBProvider.name == payload.name))).scalar_one_or_none()
                if existing:
                    raise HTTPException(status_code=400, detail=f"Provider with name '{payload.name}' already exists.")
                
                p = DBProvider(
                    name=payload.name,
                    base_url=payload.base_url.rstrip("/"),
                    model=payload.model,
                    priority=payload.priority,
                    enabled=payload.enabled,
                    timeout_ms=int(payload.timeout_s * 1000),
                )
                if payload.api_key:
                    p.api_key = payload.api_key
                sess.add(p)
                await sess.commit()
                await sess.refresh(p)
                new_provider_id = p.id
            await sync_router_providers(services.router)
            broadcaster.broadcast("providers_changed", {"action": "create", "id": new_provider_id, "name": payload.name})
            broadcaster.broadcast("overview_changed", {})
            return {"ok": True, "id": new_provider_id, "message": "Provider created and router reloaded."}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database error creating provider: {exc}")

    # File-backed persistence (data/providers.json)
    stored = load_stored_providers()
    if any(p["name"].lower() == payload.name.lower() for p in stored):
        raise HTTPException(status_code=400, detail=f"Provider with name '{payload.name}' already exists.")

    next_id = max([p.get("id", 0) for p in stored], default=0) + 1
    new_entry = {
        "id": next_id,
        "name": payload.name,
        "base_url": payload.base_url.rstrip("/"),
        "api_key": payload.api_key or "",
        "model": payload.model,
        "priority": payload.priority,
        "enabled": payload.enabled,
        "timeout_s": payload.timeout_s,
    }
    stored.append(new_entry)
    save_stored_providers(stored)
    await sync_router_providers(services.router)
    broadcaster.broadcast("providers_changed", {"action": "create", "id": next_id, "name": payload.name})
    broadcaster.broadcast("overview_changed", {})

    return {"ok": True, "id": next_id, "message": "Provider created and saved to disk."}


@router.put("/providers/{provider_id}", dependencies=[Depends(require_admin)])
async def update_provider(provider_id: str, payload: ProviderPayload, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                p = None
                if provider_id.isdigit():
                    p = (await sess.execute(select(DBProvider).where(DBProvider.id == int(provider_id)))).scalar_one_or_none()
                if not p:
                    p = (await sess.execute(select(DBProvider).where(DBProvider.name == payload.name))).scalar_one_or_none()
                if not p:
                    p = (await sess.execute(select(DBProvider).where(DBProvider.name == provider_id))).scalar_one_or_none()
                
                if p:
                    p.name = payload.name
                    p.base_url = payload.base_url.rstrip("/")
                    p.model = payload.model
                    p.priority = payload.priority
                    p.enabled = payload.enabled
                    p.timeout_ms = int(payload.timeout_s * 1000)
                    if payload.api_key:
                        p.api_key = payload.api_key
                    await sess.commit()
                    await sync_router_providers(services.router)
                    broadcaster.broadcast("providers_changed", {"action": "update", "id": provider_id, "name": payload.name})
                    broadcaster.broadcast("overview_changed", {})
                    return {"ok": True, "message": "Provider updated and router reloaded."}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database error updating provider: {exc}")

    # File-backed persistence
    stored = load_stored_providers()
    found = False
    for p in stored:
        is_target = (
            str(p.get("id")) == str(provider_id)
            or p.get("name") == provider_id
            or p.get("name") == payload.name
        )
        if is_target:
            found = True
            p["name"] = payload.name
            p["base_url"] = payload.base_url.rstrip("/")
            if payload.api_key:
                p["api_key"] = payload.api_key
            p["model"] = payload.model
            p["priority"] = payload.priority
            p["enabled"] = payload.enabled
            p["timeout_s"] = payload.timeout_s
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found.")

    save_stored_providers(stored)
    await sync_router_providers(services.router)
    broadcaster.broadcast("providers_changed", {"action": "update", "id": provider_id, "name": payload.name})
    broadcaster.broadcast("overview_changed", {})
    return {"ok": True, "message": "Provider updated and saved to disk."}


@router.delete("/providers/{provider_id}", dependencies=[Depends(require_admin)])
async def delete_provider(provider_id: str, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                p = None
                if provider_id.isdigit():
                    p = (await sess.execute(select(DBProvider).where(DBProvider.id == int(provider_id)))).scalar_one_or_none()
                if not p:
                    p = (await sess.execute(select(DBProvider).where(DBProvider.name == provider_id))).scalar_one_or_none()
                if p:
                    await sess.delete(p)
                    await sess.commit()
                    await sync_router_providers(services.router)
                    broadcaster.broadcast("providers_changed", {"action": "delete", "id": provider_id})
                    broadcaster.broadcast("overview_changed", {})
                    return {"ok": True, "message": "Provider deleted and router reloaded."}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database error deleting provider: {exc}")

    # File-backed persistence
    stored = load_stored_providers()
    orig_len = len(stored)
    stored = [
        p for p in stored
        if str(p.get("id")) != str(provider_id) and p.get("name") != provider_id
    ]

    if len(stored) == orig_len:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found.")

    save_stored_providers(stored)
    await sync_router_providers(services.router)
    broadcaster.broadcast("providers_changed", {"action": "delete", "id": provider_id})
    broadcaster.broadcast("overview_changed", {})
    return {"ok": True, "message": "Provider deleted and removed from disk."}



@router.post("/providers/test", dependencies=[Depends(require_admin)])
async def test_provider(req: TestProviderRequest):
    """Test AI provider connection and return latency and completion sample."""
    t0 = time.monotonic()
    base = req.base_url.rstrip("/")
    api_key = (req.api_key or "").strip()

    # 1. If key is blank or contains masked bullet characters (•), retrieve real unmasked key
    if not api_key or "•" in api_key:
        if dbmod.is_configured():
            try:
                from sqlalchemy import select
                async with dbmod.session() as sess:
                    p = None
                    if req.id is not None and str(req.id).isdigit():
                        p = (await sess.execute(select(DBProvider).where(DBProvider.id == int(req.id)))).scalar_one_or_none()
                    if not p and req.id is not None:
                        p = (await sess.execute(select(DBProvider).where(DBProvider.name == str(req.id)))).scalar_one_or_none()
                    if not p:
                        p = (await sess.execute(select(DBProvider).where(DBProvider.base_url == base, DBProvider.model == req.model))).scalars().first()
                    if p and p.api_key:
                        api_key = p.api_key
            except Exception:
                pass
        if not api_key or "•" in api_key:
            stored = load_stored_providers()
            for p in stored:
                is_match = (
                    (req.id is not None and (str(p.get("id")) == str(req.id) or p.get("name") == str(req.id)))
                    or (p.get("base_url", "").rstrip("/") == base and p.get("model") == req.model)
                )
                if is_match and p.get("api_key"):
                    api_key = p["api_key"]
                    break

    # 2. Check if key is available
    if not api_key:
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": 0,
            "error": "No API key configured for this provider. Please enter a valid API key.",
        }

    # 3. Validate header encoding safety
    try:
        api_key.encode("latin-1")
    except UnicodeEncodeError:
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": 0,
            "error": "API Key contains invalid non-ASCII characters (such as masked '•' dots). Please leave the field blank to use the stored unmasked key.",
        }

    is_anthropic = "anthropic.com" in base or base.endswith("/messages")

    if is_anthropic:
        url = base if base.endswith("/messages") else f"{base}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": req.model,
            "max_tokens": 50,
            "system": "You are a translator. Translate the word to Myanmar.",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.1,
        }
    else:
        url = base + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": "You are a translator. Translate the word to Myanmar."},
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 50,
            "temperature": 0.1,
        }


    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=req.timeout_s)
            latency_ms = int((time.monotonic() - t0) * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                if is_anthropic:
                    content = data["content"][0]["text"].strip()
                else:
                    content = data["choices"][0]["message"]["content"].strip()
                return {
                    "ok": True,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "model": req.model,
                    "sample_output": content,
                }
            else:
                err_detail = ""
                try:
                    err_json = resp.json()
                    err_detail = err_json.get("error", {}).get("message", resp.text[:200])
                except Exception:
                    err_detail = resp.text[:200]
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "error": err_detail,
                }
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {
                "ok": False,
                "status_code": 0,
                "latency_ms": latency_ms,
                "error": f"{type(exc).__name__}: {exc}",
            }


# ---- Staff / Users Management ---------------------------------------------

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(request: Request):
    services: Services = request.app.state.services
    users = []
    seen_ids: set[int] = set()

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                result = await sess.execute(select(AllowedUser).order_by(AllowedUser.created_at.desc()))
                rows = result.scalars().all()
                for r in rows:
                    seen_ids.add(r.user_id)
                    users.append({
                        "user_id": r.user_id,
                        "display_name": r.display_name,
                        "username": r.username,
                        "role": r.role,
                        "daily_soft_cap": r.daily_soft_cap,
                        "active": r.active,
                        "last_active_at": r.last_active_at.astimezone(YANGON).isoformat() if r.last_active_at else None,
                        "created_at": to_mmt_str(r.created_at, "%Y-%m-%d %H:%M"),
                    })
        except Exception:
            pass

    # Merge discovered users from memory if any
    if hasattr(services.user_store, "get_discovered_users"):
        discovered = services.user_store.get_discovered_users()
        for d in discovered:
            uid = d.get("user_id")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                users.append({
                    "user_id": uid,
                    "display_name": d.get("display_name"),
                    "username": d.get("username"),
                    "role": d.get("role", "staff"),
                    "daily_soft_cap": d.get("daily_soft_cap", 200),
                    "active": d.get("active", True),
                    "last_active_at": d.get("last_active_at"),
                    "created_at": d.get("created_at"),
                })

    # Fallback to seeded env users if not already in list
    for uid in config.ADMIN_USER_IDS:
        if uid not in seen_ids:
            seen_ids.add(uid)
            users.append({
                "user_id": uid,
                "display_name": "Admin (Env)",
                "username": None,
                "role": "admin",
                "daily_soft_cap": 500,
                "active": True,
                "last_active_at": None,
                "created_at": None,
            })
    for uid in config.ALLOWED_USER_IDS:
        if uid not in seen_ids:
            seen_ids.add(uid)
            users.append({
                "user_id": uid,
                "display_name": "Staff (Env)",
                "username": None,
                "role": "staff",
                "daily_soft_cap": 200,
                "active": True,
                "last_active_at": None,
                "created_at": None,
            })
    return {"users": users}


@router.post("/users", dependencies=[Depends(require_admin)])
async def add_or_update_user(payload: UserPayload, request: Request):
    services: Services = request.app.state.services

    if not dbmod.is_configured():
        if hasattr(services.user_store, "_discovered_users"):
            services.user_store._discovered_users[payload.user_id] = {
                "user_id": payload.user_id,
                "display_name": payload.display_name,
                "username": payload.username,
                "role": payload.role,
                "daily_soft_cap": payload.daily_soft_cap,
                "active": payload.active,
                "last_active_at": datetime.datetime.now(YANGON).isoformat(),
                "created_at": datetime.datetime.now(YANGON).strftime("%Y-%m-%d %H:%M"),
            }
            services.user_store.invalidate(payload.user_id)
            broadcaster.broadcast("users_changed", {"action": "save", "user_id": payload.user_id})
            return {"ok": True, "message": "User saved."}
        raise HTTPException(status_code=400, detail="Database is not configured to persist dynamic users.")

    from sqlalchemy import select

    async with dbmod.session() as sess:
        existing = (await sess.execute(select(AllowedUser).where(AllowedUser.user_id == payload.user_id))).scalar_one_or_none()
        if existing:
            existing.display_name = payload.display_name or existing.display_name
            if payload.username is not None:
                existing.username = payload.username
            existing.role = payload.role
            existing.daily_soft_cap = payload.daily_soft_cap
            existing.active = payload.active
        else:
            u = AllowedUser(
                user_id=payload.user_id,
                display_name=payload.display_name,
                username=payload.username,
                role=payload.role,
                daily_soft_cap=payload.daily_soft_cap,
                active=payload.active,
            )
            sess.add(u)
        await sess.commit()

    # Invalidate memory cache
    services.user_store.invalidate(payload.user_id)
    broadcaster.broadcast("users_changed", {"action": "save", "user_id": payload.user_id})
    return {"ok": True, "message": "User saved."}


@router.patch("/users/{user_id}/status", dependencies=[Depends(require_admin)])
async def toggle_user_status(user_id: int, payload: UserStatusPayload, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        from sqlalchemy import select

        async with dbmod.session() as sess:
            u = (await sess.execute(select(AllowedUser).where(AllowedUser.user_id == user_id))).scalar_one_or_none()
            if u:
                u.active = payload.active
                await sess.commit()

    if hasattr(services.user_store, "_discovered_users") and user_id in services.user_store._discovered_users:
        services.user_store._discovered_users[user_id]["active"] = payload.active

    services.user_store.invalidate(user_id)
    try:
        group_id = config.GROUP_CHAT_ID
        if group_id:
            await services.cache.delete(f"grp:{group_id}:{user_id}")
    except Exception:
        pass
    broadcaster.broadcast("users_changed", {"action": "status_toggle", "user_id": user_id, "active": payload.active})
    return {"ok": True, "user_id": user_id, "active": payload.active}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        from sqlalchemy import select

        async with dbmod.session() as sess:
            u = (await sess.execute(select(AllowedUser).where(AllowedUser.user_id == user_id))).scalar_one_or_none()
            if u:
                await sess.delete(u)
                await sess.commit()

    if hasattr(services.user_store, "_discovered_users"):
        services.user_store._discovered_users.pop(user_id, None)

    services.user_store.invalidate(user_id)
    try:
        group_id = config.GROUP_CHAT_ID
        if group_id:
            await services.cache.delete(f"grp:{group_id}:{user_id}")
    except Exception:
        pass
    broadcaster.broadcast("users_changed", {"action": "delete", "user_id": user_id})
    return {"ok": True, "message": "User deleted."}


# ---- Playground & Policy Preview ------------------------------------------

@router.post("/playground", dependencies=[Depends(require_admin)])
async def test_playground(req: PlaygroundRequest, request: Request):
    services: Services = request.app.state.services
    t0 = time.monotonic()
    
    # 1. Script detection & auto-toggle
    detected = _dominant_script(req.text)
    src_lang = "en" if detected == "latin" else "my"
    dst_lang = req.dst or resolve_toggle_dst(src_lang, "en")
    
    # 2. Entity & Term policy handling (aligned with asymmetric translate_policied)
    protected_text, entity_restore = protect_entities(req.text)

    if dst_lang == "my":
        # Relaxed path: Global -> Myanmar (unmasked, natural colleague phrasing)
        masked_text = protected_text
        policy_hits = []
        system_prompt = build_system_prompt(src_lang, dst_lang, services.policy)
        try:
            raw_output, provider_name = await services.router.translate(protected_text, system_prompt)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "src_lang": src_lang,
                "dst_lang": dst_lang,
                "masked_text": masked_text,
                "policy_hits": [],
            }
        denial_hits = []
        final_output = restore_entities(raw_output, entity_restore)
        final_output = sanitize_leaks(final_output, dst="my")
    else:
        # Full policy path: Myanmar -> English (term masking + repair)
        masked_text = mask(protected_text, src_lang, services.policy)
        policy_hits = [m.group(1) for m in PLACEHOLDER_RE.finditer(masked_text)]
        system_prompt = build_system_prompt(src_lang, dst_lang, services.policy)
        try:
            raw_output, provider_name = await services.router.translate(masked_text, system_prompt)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "src_lang": src_lang,
                "dst_lang": dst_lang,
                "masked_text": masked_text,
                "policy_hits": list(policy_hits),
            }
        rendered_output = render(raw_output, dst_lang, services.policy)
        denial_hits = deny_scan(rendered_output, dst_lang, services.policy)
        if denial_hits:
            try:
                from ..policy.policy import strict_suffix
                raw_output, provider_name = await services.router.translate(
                    masked_text, system_prompt + strict_suffix(denial_hits), force=provider_name
                )
                rendered_output = render(raw_output, dst_lang, services.policy)
                denial_hits = deny_scan(rendered_output, dst_lang, services.policy)
            except Exception:
                pass
        sanitized_output = sanitize_leaks(rendered_output, dst_lang)
        final_output = restore_entities(sanitized_output, entity_restore)
        final_output = sanitize_leaks(final_output, dst=dst_lang)
    latency_ms = int((time.monotonic() - t0) * 1000)

    try:
        services.stats.record_usage_log({
            "user_id": 999999,
            "char_len": len(req.text),
            "provider": provider_name,
            "latency_ms": latency_ms,
            "status": 200,
            "policy_hits": list(set(policy_hits)),
        })
    except Exception:
        pass

    return {
        "ok": True,
        "src_lang": src_lang,
        "dst_lang": dst_lang,
        "provider_used": provider_name,
        "latency_ms": latency_ms,
        "masked_input": masked_text,
        "policy_hits": list(set(policy_hits)),
        "raw_output": raw_output,
        "denial_hits": denial_hits,
        "final_output": final_output,
    }


# ---- Audit Logs -----------------------------------------------------------

def _parse_ts_param(val: Optional[str]) -> Optional[float]:
    """Parse timestamp string (epoch seconds, milliseconds, or ISO/date string) to float seconds."""
    if not val:
        return None
    val = str(val).strip()
    try:
        if val.replace(".", "", 1).isdigit():
            num = float(val)
            if num > 1e11:  # JavaScript timestamp in milliseconds
                return num / 1000.0
            return num
    except Exception:
        pass
    from datetime import datetime, timezone
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val[:19], fmt).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(val).timestamp()
    except Exception:
        return None


@router.get("/logs", dependencies=[Depends(require_admin)])
async def get_logs(
    request: Request,
    limit: int = 100,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    provider: Optional[str] = None,
):
    services: Services = request.app.state.services
    start_ts = _parse_ts_param(start_time)
    end_ts = _parse_ts_param(end_time)

    user_names: dict[int, dict] = {}
    for uid in config.ADMIN_USER_IDS:
        user_names[uid] = {"display_name": "Admin (Env)", "username": None}
    for uid in config.ALLOWED_USER_IDS:
        user_names[uid] = {"display_name": "Staff (Env)", "username": None}

    if hasattr(services.user_store, "get_discovered_users"):
        for d in services.user_store.get_discovered_users():
            uid = d.get("user_id")
            if uid:
                user_names[uid] = {
                    "display_name": d.get("display_name"),
                    "username": d.get("username"),
                }

    if dbmod.is_configured():
        try:
            from sqlalchemy import select
            async with dbmod.session() as sess:
                rows = (await sess.execute(select(AllowedUser.user_id, AllowedUser.display_name, AllowedUser.username))).all()
                for uid, dname, uname in rows:
                    user_names[uid] = {"display_name": dname, "username": uname}
        except Exception:
            pass

    def _format_log(raw: dict) -> dict:
        st = raw.get("status", 200)
        norm_status = 200 if st == "ok" else st
        prov = raw.get("provider")
        if not prov or prov == "unknown":
            prov = "cache" if raw.get("cache_hit") else "default"
        uid = raw.get("user_id", 0)
        u_info = user_names.get(uid, {})
        raw_ts = raw.get("timestamp")
        created_at = raw.get("created_at")
        if raw_ts is not None and not created_at:
            ts_sec = raw_ts / 1000.0 if raw_ts > 1e11 else float(raw_ts)
            created_at = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc).astimezone(YANGON).strftime("%Y-%m-%d %H:%M:%S")
        ts_ms = int(raw_ts * 1000) if raw_ts and raw_ts < 1e11 else raw_ts
        return {
            "id": raw.get("id"),
            "timestamp": ts_ms,
            "user_id": uid,
            "display_name": raw.get("display_name") or u_info.get("display_name"),
            "username": raw.get("username") or u_info.get("username"),
            "char_len": raw.get("char_len", 0),
            "provider": prov,
            "latency_ms": raw.get("latency_ms", 0),
            "status": norm_status,
            "policy_hits": raw.get("policy_hits") or [],
            "created_at": created_at,
        }

    def _filter_in_memory(items: list[dict]) -> list[dict]:
        out = []
        for raw in items:
            raw_ts = raw.get("timestamp")
            if raw_ts is not None and raw_ts > 1e11:
                raw_ts = raw_ts / 1000.0
            if raw_ts is None and raw.get("created_at"):
                raw_ts = _parse_ts_param(raw.get("created_at"))
            if start_ts is not None and raw_ts is not None and raw_ts < start_ts:
                continue
            if end_ts is not None and raw_ts is not None and raw_ts > end_ts:
                continue
            if provider and provider != "all":
                item_prov = (raw.get("provider") or "").lower()
                if item_prov != provider.lower():
                    continue
            out.append(_format_log(raw))
            if len(out) >= limit:
                break
        return out

    if not dbmod.is_configured():
        return {"logs": _filter_in_memory(list(services.stats.recent_logs))}
    
    try:
        from datetime import datetime, timezone
        from sqlalchemy import select

        async with dbmod.session() as sess:
            query = select(UsageLog).order_by(UsageLog.ts.desc())
            if start_ts is not None:
                query = query.where(UsageLog.ts >= datetime.fromtimestamp(start_ts, tz=timezone.utc))
            if end_ts is not None:
                query = query.where(UsageLog.ts <= datetime.fromtimestamp(end_ts, tz=timezone.utc))
            if provider and provider != "all":
                query = query.where(UsageLog.provider == provider)

            query = query.limit(limit)
            result = await sess.execute(query)
            rows = result.scalars().all()
            logs = []
            for r in rows:
                u_info = user_names.get(r.user_id, {})
                ts_ms = int(r.ts.timestamp() * 1000) if r.ts else None
                logs.append({
                    "id": r.id,
                    "timestamp": ts_ms,
                    "user_id": r.user_id,
                    "display_name": u_info.get("display_name"),
                    "username": u_info.get("username"),
                    "char_len": r.char_len,
                    "provider": getattr(r, "provider", None) or ("cache" if getattr(r, "cache_hit", False) else "default"),
                    "latency_ms": r.latency_ms,
                    "status": 200 if r.status in ("ok", "200") else r.status,
                    "policy_hits": r.policy_hits or [],
                    "created_at": to_mmt_str(r.ts, "%Y-%m-%d %H:%M:%S"),
                })
            if logs:
                return {"logs": logs}
            return {"logs": _filter_in_memory(list(services.stats.recent_logs))}
    except Exception:
        return {"logs": _filter_in_memory(list(services.stats.recent_logs))}


