"""The policy regression set: 40 cases, the single source of truth.

Spec section 4.5 makes this artefact mandatory: "Regression set of 40
cases ... A version cannot be published unless all 40 pass", and section 14
calls it "the artefact that keeps the bot correct over time".

One list, three consumers, so expectations can never drift apart again:
  * tests/test_regression_set.py  - runs all 40 on every commit
  * app.policy.governance         - blocks publishing a failing version
  * app.store.seed                - writes the same 40 rows to policy_tests

The runner is DETERMINISTIC and needs no provider: it exercises the part of
the pipeline this project owns - normalise -> entity protection -> mask ->
render -> restore - exactly as `translate_policied` calls it, minus the
provider hop. Provider-dependent behaviour (does the model obey the prompt?)
is checked by the same cases through `run_live`, behind
PYTEST_LIVE_PROVIDER=1, because section 4.6 requires the set to be run
against every provider before it goes live.

Adding a case: append a RegressionCase. Keep the coverage matrix below true.

Coverage matrix (40 cases) - v2026-09-20 relaxed Global->MY:
  concept     user_id  user_account  balance  platform  member
  my -> en        5          2          3        2        1   (full policy)
  en -> my        2          1          3        1        2   (relaxed: literal, no mask)
  en -> en        1          2          3        1        1   (full policy - neutralised)
  zh -> en        1          1          1        1        1   (full policy)
  mixed (auto)    2          0          1        0        0   (my->en policied, *->my relaxed)
  entities/evasion/traps: 7 (URL, mention, number, /command, zero-width x2,
                            word-boundary)
  Note: en->my and auto->my are now relaxed (dst==my bypasses mask/render/deny)
  so Game Point stays as ဂိမ်းပွိုင့် etc. for Myanmar output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .policy import (
    deny_scan,
    mask,
    normalise,
    protect_entities,
    render,
    restore_entities,
)

if TYPE_CHECKING:
    from .policy import Policy


@dataclass(frozen=True)
class RegressionCase:
    """One deterministic expectation about the policy pipeline.

    Mirrors the policy_tests schema: expected_contains / must_not_contain.
    """

    id: str
    src: str
    dst: str
    text: str
    must_contain: str
    must_not_contain: str = ""
    note: str = ""


REGRESSION_SET: list[RegressionCase] = [
    # -- my -> en ---------------------------------------------------------
    RegressionCase(
        "my_en_user_id_aing", "my", "en", "ဂိမ်းအိုင်ဒီ မှားနေတယ်",
        "User ID", "ဂိမ်း", "spec 4.4 few-shot input (aing spelling)",
    ),
    RegressionCase(
        "my_en_user_id_aik", "my", "en", "ဂိမ်းအိုက်ဒီ ပြန်စစ်ပေးပါ",
        "User ID", "ဂိမ်း", "the aik transliteration of the same concept",
    ),
    RegressionCase(
        "my_en_account", "my", "en", "ဂိမ်းအကောင့် ဖွင့်လို့မရဘူး",
        "User Account", "ဂိမ်း", "account must win over bare platform",
    ),
    RegressionCase(
        "my_en_points", "my", "en", "ပွိုင့်တွေ ဘယ်လိုလွှဲမလဲ",
        "Amount", "ဂိမ်း", "owner term choice 2026-09-19: Amount",
    ),
    RegressionCase(
        "my_en_game_points", "my", "en", "ဂိမ်းပွိုင့် လက်ကျန်စစ်ပေးပါ",
        "Amount", "ဂိမ်း", "longest match: ဂိမ်းပွိုင့် before ဂိမ်း",
    ),
    RegressionCase(
        "my_en_game_marks", "my", "en", "ဂိမ်းအမှတ် ဘယ်လောက်ကျန်လဲ",
        "Amount", "ဂိမ်း", "variant added in v3.2",
    ),
    RegressionCase(
        "my_en_platform", "my", "en", "ဂိမ်းထဲက အကောင့်ပြန်ဖွင့်ပေးပါ",
        "Platform", "ဂိမ်း", "ဂိမ်းထဲ is a platform variant",
    ),
    RegressionCase(
        "my_en_platform_bare", "my", "en", "ဂိမ်း ထဲမှာ ဝင်လို့မရဘူး",
        "Platform", "ဂိမ်း", "bare ဂိမ်း masks as platform",
    ),
    RegressionCase(
        "my_en_member", "my", "en", "ကစားသမား တစ်ယောက် ငြင်းနေတယ်",
        "Customer", "ကစားသမား", "member approved 2026-09-19",
    ),
    RegressionCase(
        "my_en_member_and_id", "my", "en",
        "ကစားသမားရဲ့ ဂိမ်းအိုင်ဒီ ကို စစ်ပေးပါ",
        "User ID", "ဂိမ်း", "two concepts in one sentence",
    ),
    RegressionCase(
        "my_en_number_entity", "my", "en",
        "ဂိမ်းအိုင်ဒီ 0912345678 ကို စစ်ပေးပါ",
        "0912345678", "ဂိမ်း", "phone number survives verbatim",
    ),
    RegressionCase(
        "my_en_url_entity", "my", "en",
        "https://x.co/a မှာ ဂိမ်းအကောင့် ဖွင့်ပါ",
        "https://x.co/a", "ဂိမ်း", "URL survives verbatim",
    ),
    # -- en -> my ---------------------------------------------------------
    RegressionCase(
        "en_my_user_id", "en", "my", "my game id is wrong",
        "game id", "အသုံးပြုသူ ID", "relaxed Global->MY: literal, no mask",
    ),
    RegressionCase(
        "en_my_account", "en", "my", "check my game account",
        "game account", "အသုံးပြုသူ အကောင့်", "relaxed: literal",
    ),
    RegressionCase(
        "en_my_points", "en", "my", "how do I transfer my game points",
        "game points", "ပမာဏ", "relaxed Global->MY: literal, Game Point stays",
    ),
    RegressionCase(
        "en_my_chips", "en", "my", "the chips were not credited",
        "chips", "ပမာဏ", "relaxed: literal",
    ),
    RegressionCase(
        "en_my_member", "en", "my", "the player is complaining",
        "player", "ဖောက်သည်", "relaxed: literal",
    ),
    RegressionCase(
        "en_my_platform", "en", "my", "in-game items are missing",
        "in-game", "ပလက်ဖောင်း", "relaxed: literal",
    ),
    RegressionCase(
        "en_my_gid_with_number", "en", "my", "gid 12345 not found",
        "gid", "အသုံးပြုသူ ID", "relaxed: literal, number survives",
    ),
    RegressionCase(
        "en_my_command_entity", "en", "my", "/tr game points now",
        "game points", "ပမာဏ", "relaxed: literal, /command protected",
    ),
    # -- en -> en (vocabulary neutralised without a language change) ------
    RegressionCase(
        "en_en_user_id", "en", "en", "my game id is wrong",
        "User ID", "game id",
    ),
    RegressionCase(
        "en_en_gaming_account", "en", "en", "the gaming account is locked",
        "User Account", "gaming account",
    ),
    RegressionCase(
        "en_en_player_account", "en", "en", "player account not found",
        "User Account", "player account",
        "longest match: player account before player",
    ),
    RegressionCase(
        "en_en_points_with_number", "en", "en",
        "transfer my points to 0912345678",
        "Amount", "points", "number survives verbatim",
    ),
    RegressionCase(
        "en_en_coins", "en", "en", "coins missing after top up",
        "Amount", "coins",
    ),
    RegressionCase(
        "en_en_member", "en", "en", "the bettor asks about the top up",
        "Customer", "bettor",
    ),
    RegressionCase(
        "en_en_platform", "en", "en", "ingame rewards missing",
        "Platform", "ingame",
    ),
    RegressionCase(
        "en_en_entities_verbatim", "en", "en",
        "https://x.co/a @ops game id 42",
        "https://x.co/a", "game id", "URL + mention + number all verbatim",
    ),
    RegressionCase(
        "en_en_case_insensitive", "en", "en", "GAME POINTS balance check",
        "Amount", "GAME POINTS", "masking is case-insensitive",
    ),
    RegressionCase(
        "en_en_no_false_positive_checkpoint", "en", "en", "checkpoint reached",
        "checkpoint", "Amount", "'points' must not match inside 'checkpoint'",
    ),
    # -- zh -> en (zh input is rejected at Gate 6 since v3.2; the mapping is
    #    retained for a possible re-enable, so it stays under test) --------
    RegressionCase(
        "zh_en_platform_balance", "zh", "en", "游戏里的积分怎么转",
        "Amount", "游戏", "spec 4.4 few-shot, longest match first",
    ),
    RegressionCase(
        "zh_en_account", "zh", "en", "游戏账号不对",
        "User Account", "游戏",
    ),
    RegressionCase(
        "zh_en_member_and_id", "zh", "en", "玩家的游戏ID是多少",
        "User ID", "游戏",
    ),
    # -- mixed language (the normal case in real chats) -------------------
    RegressionCase(
        "auto_en_mixed_id", "auto", "en", "ဂိမ်းအိုင်ဒီ ကို check လုပ်ပေးပါ",
        "User ID", "ဂိမ်း", "Burmese + English in one message",
    ),
    RegressionCase(
        "auto_my_mixed_points", "auto", "my", "please ပွိုင့် transfer လုပ်ပေးပါ",
        "ပွိုင့်", "ပမာဏ", "relaxed Global->MY: literal, no mask",
    ),
    # -- evasion and boundary traps --------------------------------------
    RegressionCase(
        "auto_en_zero_width_myanmar", "auto", "en",
        "ဂိ\u200bမ်းအိုင်ဒီ စစ်ပေးပါ",
        "User ID", "ဂိမ်း", "zero-width space must not split a concept",
    ),
    RegressionCase(
        "en_en_zero_width_english", "en", "en", "my game\u200bid is wrong",
        "User ID", "game id", "zero-width space must not split a concept",
    ),
    RegressionCase(
        "en_en_mention_entity", "en", "en", "@ops check the game account",
        "@ops", "game account", "mention survives verbatim",
    ),
    RegressionCase(
        "en_en_no_false_positive_gamer", "en", "en", "the gamer forum is quiet",
        "gamer", "Customer", "'gamer' is not a concept variant",
    ),
    RegressionCase(
        "en_en_no_false_positive_point", "en", "en", "point of view differs",
        "point of view", "Amount", "'points' must not match 'point'",
    ),
]


# Deny-scan and evasion cases. These assert Layer 3 behaviour rather than a
# rendered term, so they are tested directly instead of being written to
# policy_tests (whose schema holds only contains / must_not_contain).
@dataclass(frozen=True)
class DenyCase:
    id: str
    dst: str
    text: str
    must_hit: tuple[str, ...] = ()
    note: str = ""


DENY_CASES: list[DenyCase] = [
    DenyCase("deny_en_game", "en", "this is a game", ("game",)),
    DenyCase("deny_en_hyphen_evasion", "en", "play g-a-m-e now", ("game",)),
    DenyCase("deny_en_spaced_evasion", "en", "play g a m e now", ("game",)),
    DenyCase("deny_en_dotted_evasion", "en", "play G.A.M.E now", ("game",)),
    DenyCase("deny_en_zero_width_evasion", "en", "play g\u200bam\u200be now",
             ("game",)),
    DenyCase("deny_my_bare", "my", "ဂိမ်းအကြောင်း", ("ဂိမ်း",)),
    DenyCase("deny_zh_hyphen_evasion", "zh", "来赌-场玩", ("赌场",)),
    DenyCase("clean_en", "en", "How do I transfer the Amount?", ()),
    DenyCase("clean_my", "my", "ပမာဏ ဘယ်လိုလွှဲမလဲ", ()),
]


def evaluate(case: RegressionCase, policy: "Policy") -> str:
    """Run the deterministic half of the pipeline and return the final text.

    Mirrors translate_policied: dst==my is relaxed (no mask/render), dst==en
    is fully policied.
    """
    protected, restore = protect_entities(normalise(case.text))
    if case.dst == "my":
        # Relaxed Global->MY: literal, no term-policy
        return restore_entities(protected, restore)
    masked = mask(protected, case.src, policy)
    rendered = render(masked, case.dst, policy)
    return restore_entities(rendered, restore)


def check(case: RegressionCase, policy: "Policy") -> list[str]:
    """Return the list of failures for *case*; empty means it passes."""
    final = evaluate(case, policy)
    problems: list[str] = []
    if case.must_contain and case.must_contain not in final:
        problems.append(f"missing {case.must_contain!r}")
    if case.must_not_contain and case.must_not_contain in final:
        problems.append(f"still contains {case.must_not_contain!r}")
    return problems


def run_all(policy: "Policy") -> dict[str, list[str]]:
    """{case_id: [problems]} for every case in the set."""
    return {case.id: check(case, policy) for case in REGRESSION_SET}


def check_deny(case: DenyCase, policy: "Policy") -> list[str]:
    hits = tuple(deny_scan(case.text, case.dst, policy))
    if set(case.must_hit) <= set(hits):
        return []
    return [f"deny_scan returned {list(hits)}, expected {list(case.must_hit)}"]


async def run_live(
    policy: "Policy", router, provider_name: str | None = None
) -> dict[str, list[str]]:
    """Optional: push the same 40 cases through a real provider (spec 4.6).

    Enable with PYTEST_LIVE_PROVIDER=1 and a configured provider. Slower and
    costs credits, so it never runs by default.
    """
    from .policy import build_system_prompt

    results: dict[str, list[str]] = {}
    for case in REGRESSION_SET:
        protected, restore = protect_entities(normalise(case.text))
        if case.dst == "my":
            masked = protected
            prompt = build_system_prompt(case.src, case.dst, policy)
            out, _ = await router.translate(masked, prompt, force=provider_name)
            final = restore_entities(out, restore)
        else:
            masked = mask(protected, case.src, policy)
            prompt = build_system_prompt(case.src, case.dst, policy)
            out, _ = await router.translate(masked, prompt, force=provider_name)
            final = restore_entities(render(out, case.dst, policy), restore)
        problems: list[str] = []
        if case.must_contain and case.must_contain not in final:
            problems.append(f"missing {case.must_contain!r}")
        if case.must_not_contain and case.must_not_contain in final:
            problems.append(f"still contains {case.must_not_contain!r}")
        leaks = deny_scan(final, case.dst, policy)
        if leaks:
            problems.append(f"deny terms leaked: {leaks}")
        results[case.id] = problems
    return results
