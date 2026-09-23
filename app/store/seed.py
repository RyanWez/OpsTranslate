"""Idempotent database seeder.

Creates tables (if missing) and seeds:
  - allowed_users from ALLOWED_USER_IDS (staff) and ADMIN_USER_IDS (admin)
  - settings: max_input_chars = config.MAX_INPUT_CHARS
  - policy_versions v1 (published) with the section 4.2 mapping,
    per-language deny lists, and a starter regression set
  - prompts: the default system-prompt reference row

NOTE: providers are NOT seeded from env - they live ONLY in the DB and are
managed via the /admin Providers page (Admin Panel is the source of truth).
An empty providers table after deploy means the admin has added none yet.

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
    Setting,
    TermConcept,
    TermOutput,
    TermVariant,
)
from ..policy.governance import regression_report
from ..policy.policy import build_system_prompt, compile_policy
from ..policy.policy_data import CONCEPTS, DENY_TERMS
from ..policy.regression_set import REGRESSION_SET

log = logging.getLogger("opstranslate.seed")


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
            sess.add(Setting(key="max_input_chars", value={"value": config.MAX_INPUT_CHARS}))

        # --- policy v1 -----------------------------------------------------
        version = config.POLICY_VERSION
        pv = (
            await sess.execute(
                select(PolicyVersion).where(PolicyVersion.version == version)
            )
        ).scalar_one_or_none()
        if pv is None:
            # Spec 4.5: a version cannot be published unless the whole
            # regression set passes. A failing set seeds as draft instead.
            report = regression_report(version)
            status = "published" if report.ok else "draft"
            note = f"seeded v{version} - {report.summary()}"
            if not report.ok:
                log.error("policy v%d NOT publishable: %s", version,
                          report.failures)
            pv = PolicyVersion(version=version, status=status, note=note)
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

            # The same 40 cases pytest runs (app/policy/regression_set.py).
            for case in REGRESSION_SET:
                sess.add(
                    PolicyTest(
                        policy_version=version, src_lang=case.src,
                        dst_lang=case.dst, input_text=case.text,
                        expected_contains=case.must_contain,
                        must_not_contain=case.must_not_contain,
                    )
                )
            log.info("seeded policy v%d", version)

        # NOTE: no provider seeding - providers live ONLY in the DB, managed
        # via /admin Providers. An empty table = admin hasn't added any yet.

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
