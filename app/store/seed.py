"""Idempotent database seeder.

Creates tables (if missing) and seeds:
  - allowed_users from ALLOWED_USER_IDS (staff) and ADMIN_USER_IDS (admin)
  - settings: max_input_chars = 250
  - policy_versions v1 (published) with the section 4.2 mapping,
    per-language deny lists, and a starter regression set
  - providers: the primary provider from env
  - prompts: the default system-prompt reference row

Run:  python -m app.store.seed   (requires DATABASE_URL)
Safe to re-run: existing rows are left untouched.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from .. import config
from . import db as dbmod
from .models import (
    AllowedUser,
    Base,
    DenyTerm,
    PolicyTest,
    PolicyVersion,
    Prompt,
    Provider,
    Setting,
    TermConcept,
    TermOutput,
    TermVariant,
)
from ..policy.policy import build_system_prompt, compile_policy
from ..policy.policy_data import CONCEPTS, DENY_TERMS

log = logging.getLogger("opstranslate.seed")

# Starter regression cases: (src, dst, input, must_contain, must_not_contain).
# These run against mask/render/deny-scan only - no provider needed.
REGRESSION_SEED: list[tuple[str, str, str, str, str]] = [
    ("my", "en", "ဂိမ်းအိုင်ဒီ မှားနေတယ်", "User ID", "ဂိမ်း"),
    ("my", "en", "ပွိုင့်တွေ ဘယ်လိုလွှဲမလဲ", "Balance", "ဂိမ်း"),
    ("en", "en", "my game id is wrong", "User ID", "game id"),
    ("en", "my", "check my game points", "လက်ကျန်", "game"),
    ("zh", "en", "游戏里的积分怎么转", "balance", "游戏"),
    ("zh", "en", "游戏账号不对", "User Account", "游戏"),
    ("en", "en", "transfer my points to 0912345678", "Balance", "points"),
    ("my", "en", "ဂိမ်းထဲက အကောင့်ပြန်ဖွင့်ပေးပါ", "Platform", "ဂိမ်း"),
    ("en", "en", "GAMER points balance", "Balance", "gamer"),
    ("en", "en", "checkpoint reached", "checkpoint", "Balance"),
]


async def seed() -> None:
    if not dbmod.is_configured():
        raise SystemExit("DATABASE_URL is not set - nothing to seed.")

    engine = dbmod.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with dbmod.session() as sess:
        # --- users ---------------------------------------------------------
        for uid in config.ALLOWED_USER_IDS:
            exists = await sess.get(AllowedUser, uid)
            if exists is None:
                sess.add(AllowedUser(user_id=uid, role="staff", active=True))
        for uid in config.ADMIN_USER_IDS:
            row = await sess.get(AllowedUser, uid)
            if row is None:
                sess.add(AllowedUser(user_id=uid, role="admin", active=True))
            elif row.role != "admin":
                row.role = "admin"

        # --- settings ------------------------------------------------------
        if await sess.get(Setting, "max_input_chars") is None:
            sess.add(Setting(key="max_input_chars", value={"value": 250}))

        # --- policy v1 -----------------------------------------------------
        version = config.POLICY_VERSION
        pv = (
            await sess.execute(
                select(PolicyVersion).where(PolicyVersion.version == version)
            )
        ).scalar_one_or_none()
        if pv is None:
            pv = PolicyVersion(version=version, status="published", note="seeded v1")
            sess.add(pv)
            await sess.flush()

            for concept in CONCEPTS:
                tc = TermConcept(
                    policy_version=version,
                    concept_key=concept.key,
                    enabled=concept.enabled,
                    approved=concept.approved,
                )
                sess.add(tc)
                await sess.flush()
                for lang, variants in concept.variants.items():
                    ordered = sorted(set(variants), key=len, reverse=True)
                    for prio, variant in enumerate(ordered):
                        sess.add(
                            TermVariant(
                                concept_id=tc.id, lang=lang, pattern=variant,
                                is_source=True, priority=prio,
                            )
                        )
                for lang, term in concept.outputs.items():
                    sess.add(
                        TermOutput(concept_id=tc.id, lang=lang, output_text=term)
                    )

            for lang, terms in DENY_TERMS.items():
                for term in terms:
                    sess.add(DenyTerm(policy_version=version, lang=lang, term=term))

            for src, dst, text, contains, not_contains in REGRESSION_SEED:
                sess.add(
                    PolicyTest(
                        policy_version=version, src_lang=src, dst_lang=dst,
                        input_text=text, expected_contains=contains,
                        must_not_contain=not_contains,
                    )
                )
            log.info("seeded policy v%d", version)

        # --- providers -----------------------------------------------------
        existing = (
            await sess.execute(select(Provider).where(Provider.name == "primary"))
        ).scalar_one_or_none()
        if existing is None and config.PROVIDER_BASE_URL:
            sess.add(
                Provider(
                    name="primary", kind="openai_compatible",
                    base_url=config.PROVIDER_BASE_URL, model=config.PROVIDER_MODEL,
                    priority=1, enabled=True,
                    timeout_ms=int(config.PROVIDER_TIMEOUT_S * 1000),
                )
            )

        # --- prompts -------------------------------------------------------
        has_prompt = (
            await sess.execute(select(Prompt).where(Prompt.key == "system_translate_v1"))
        ).scalar_one_or_none()
        if has_prompt is None:
            policy = compile_policy(version)
            sess.add(
                Prompt(
                    key="system_translate_v1", version=1,
                    body=build_system_prompt("auto", "en", policy), active=True,
                )
            )

        await sess.commit()
    log.info("seed complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
