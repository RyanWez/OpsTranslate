"""Admin API router for OpsTranslate Bot."""
from __future__ import annotations

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
from ..store.providers import get_active_service_providers, sync_router_providers
from .auth import get_expected_token, is_authenticated, require_admin, verify_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 15.0


class UserPayload(BaseModel):
    user_id: int
    display_name: Optional[str] = None
    role: str = "staff"  # staff | admin
    daily_soft_cap: int = 200
    active: bool = True


class PlaygroundRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    dst: Optional[str] = None


# ---- Auth Endpoints -------------------------------------------------------

@router.post("/login")
async def login(req: LoginRequest, response: Response):
    if not verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin password.",
        )
    token = get_expected_token()
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True on HTTPS via reverse proxy
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
    return {
        "authenticated": auth,
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
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---- Policy & Term Glossary -----------------------------------------------

@router.get("/policy", dependencies=[Depends(require_admin)])
async def get_policy():
    from ..policy.policy_data import CONCEPTS, DENY_TERMS
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
        "version": config.POLICY_VERSION,
        "concepts": concepts_out,
        "deny_terms": DENY_TERMS,
    }


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
        except Exception as exc:
            pass

    # Fallback to in-memory router providers
    for p in services.router.providers:
        out.append({
            "id": None,
            "name": p.name,
            "base_url": p.base_url,
            "api_key_masked": _mask_key(p.api_key),
            "model": p.model,
            "priority": p.priority,
            "enabled": p.enabled,
            "timeout_s": p.timeout_s,
            "breaker_state": breaker_states.get(p.name, "closed"),
            "source": "memory/env",
        })
    return {"providers": out}


@router.post("/providers", dependencies=[Depends(require_admin)])
async def create_provider(payload: ProviderPayload, request: Request):
    services: Services = request.app.state.services
    new_provider_id = None

    if dbmod.is_configured():
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
    else:
        # In-memory mode (tests or DB-less deployment)
        if any(p.name == payload.name for p in services.router.providers):
            raise HTTPException(status_code=400, detail=f"Provider with name '{payload.name}' already exists.")
        new_sp = ServiceProvider(
            name=payload.name,
            base_url=payload.base_url.rstrip("/"),
            api_key=payload.api_key or "",
            model=payload.model,
            priority=payload.priority,
            enabled=payload.enabled,
            timeout_s=payload.timeout_s,
        )
        services.router.reload_providers(services.router.providers + [new_sp])

    return {"ok": True, "id": new_provider_id, "message": "Provider created and router reloaded."}


@router.put("/providers/{provider_id}", dependencies=[Depends(require_admin)])
async def update_provider(provider_id: int, payload: ProviderPayload, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        from sqlalchemy import select

        async with dbmod.session() as sess:
            p = (await sess.execute(select(DBProvider).where(DBProvider.id == provider_id))).scalar_one_or_none()
            if not p:
                raise HTTPException(status_code=404, detail="Provider not found.")
            
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
    else:
        # In-memory mode
        updated_list = []
        found = False
        for p in services.router.providers:
            if p.name == payload.name:
                found = True
                updated_list.append(ServiceProvider(
                    name=payload.name,
                    base_url=payload.base_url.rstrip("/"),
                    api_key=payload.api_key or p.api_key,
                    model=payload.model,
                    priority=payload.priority,
                    enabled=payload.enabled,
                    timeout_s=payload.timeout_s,
                ))
            else:
                updated_list.append(p)
        if not found:
            raise HTTPException(status_code=404, detail="Provider not found.")
        services.router.reload_providers(updated_list)

    return {"ok": True, "message": "Provider updated and router reloaded."}


@router.delete("/providers/{provider_id}", dependencies=[Depends(require_admin)])
async def delete_provider(provider_id: int, request: Request):
    services: Services = request.app.state.services

    if dbmod.is_configured():
        from sqlalchemy import select

        async with dbmod.session() as sess:
            p = (await sess.execute(select(DBProvider).where(DBProvider.id == provider_id))).scalar_one_or_none()
            if not p:
                raise HTTPException(status_code=404, detail="Provider not found.")
            await sess.delete(p)
            await sess.commit()
        await sync_router_providers(services.router)
    else:
        # In-memory mode: provider_id matches index or delete by priority
        if provider_id < len(services.router.providers):
            p = services.router.providers[provider_id]
            services.router.reload_providers([x for x in services.router.providers if x.name != p.name])

    return {"ok": True, "message": "Provider deleted and router reloaded."}


@router.post("/providers/test", dependencies=[Depends(require_admin)])
async def test_provider(req: TestProviderRequest):
    """Test AI provider connection and return latency and completion sample."""
    t0 = time.monotonic()
    url = req.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {req.api_key}", "Content-Type": "application/json"}
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

    if dbmod.is_configured():
        try:
            from sqlalchemy import select

            async with dbmod.session() as sess:
                result = await sess.execute(select(AllowedUser).order_by(AllowedUser.created_at.desc()))
                rows = result.scalars().all()
                for r in rows:
                    users.append({
                        "user_id": r.user_id,
                        "display_name": r.display_name,
                        "role": r.role,
                        "daily_soft_cap": r.daily_soft_cap,
                        "active": r.active,
                        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
                    })
                return {"users": users}
        except Exception:
            pass

    # Fallback to seeded env users
    for uid in config.ADMIN_USER_IDS:
        users.append({"user_id": uid, "display_name": "Admin (Env)", "role": "admin", "daily_soft_cap": 500, "active": True})
    for uid in config.ALLOWED_USER_IDS:
        if uid not in config.ADMIN_USER_IDS:
            users.append({"user_id": uid, "display_name": "Staff (Env)", "role": "staff", "daily_soft_cap": 200, "active": True})
    return {"users": users}


@router.post("/users", dependencies=[Depends(require_admin)])
async def add_or_update_user(payload: UserPayload, request: Request):
    services: Services = request.app.state.services

    if not dbmod.is_configured():
        raise HTTPException(status_code=400, detail="Database is not configured to persist dynamic users.")

    from sqlalchemy import select

    async with dbmod.session() as sess:
        existing = (await sess.execute(select(AllowedUser).where(AllowedUser.user_id == payload.user_id))).scalar_one_or_none()
        if existing:
            existing.display_name = payload.display_name or existing.display_name
            existing.role = payload.role
            existing.daily_soft_cap = payload.daily_soft_cap
            existing.active = payload.active
        else:
            u = AllowedUser(
                user_id=payload.user_id,
                display_name=payload.display_name,
                role=payload.role,
                daily_soft_cap=payload.daily_soft_cap,
                active=payload.active,
            )
            sess.add(u)
        await sess.commit()

    # Invalidate memory cache
    services.user_store.invalidate(payload.user_id)
    return {"ok": True, "message": "User saved."}


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

    services.user_store.invalidate(user_id)
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
    
    # 2. Entity & Term policy masking
    protected_text, entity_restore = protect_entities(req.text)
    masked_text = mask(protected_text, src_lang, services.policy)
    policy_hits = [m.group(1) for m in PLACEHOLDER_RE.finditer(masked_text)]
    
    # 3. Provider translation
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
    
    # 4. Deny scanning, rendering, & sanitization
    denial_hits = deny_scan(raw_output, dst_lang, services.policy)
    rendered_output = render(raw_output, dst_lang, services.policy)
    sanitized_output = sanitize_leaks(rendered_output, dst_lang)
    
    # 5. Restore entities
    final_output = restore_entities(sanitized_output, entity_restore)
    latency_ms = int((time.monotonic() - t0) * 1000)

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

@router.get("/logs", dependencies=[Depends(require_admin)])
async def get_logs(request: Request, limit: int = 50):
    if not dbmod.is_configured():
        return {"logs": []}
    
    try:
        from sqlalchemy import select

        async with dbmod.session() as sess:
            result = await sess.execute(
                select(UsageLog).order_by(UsageLog.created_at.desc()).limit(limit)
            )
            rows = result.scalars().all()
            logs = []
            for r in rows:
                logs.append({
                    "id": r.id,
                    "user_id": r.user_id,
                    "char_len": r.char_len,
                    "provider": r.provider,
                    "latency_ms": r.latency_ms,
                    "status": r.status,
                    "policy_hits": r.policy_hits,
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                })
            return {"logs": logs}
    except Exception:
        return {"logs": []}
