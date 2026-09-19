"""Seed data for the Term Policy engine, from spec section 4.2.

Each concept has source-language variants and one approved neutral output
term per target language. When the spec lists several acceptable outputs
(e.g. "Balance / Credit / Funds / Amount"), the renderer needs exactly one,
so the first listed term is used. These choices are documented here.

Note: non-English strings below are translation *data* (Locked Rule 1
allows translation data to be non-English; all code, comments and UI
strings stay English).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConceptSeed:
    key: str
    approved: bool
    enabled: bool
    # lang -> list of source variants (longest-match-first applied at load)
    variants: dict[str, list[str]] = field(default_factory=dict)
    # target lang -> approved neutral output term
    outputs: dict[str, str] = field(default_factory=dict)


CONCEPTS: list[ConceptSeed] = [
    ConceptSeed(
        key="user_id",
        approved=True,
        enabled=True,
        variants={
            # NOTE: the spec's §4.4 few-shot input uses the "အိုင်" (aing)
            # transliteration of "ID" while §4.2 lists "အိုက်" (aik). Both
            # spellings are seeded - transliteration variants are exactly
            # what this list is for. Longest-match-first keeps the compound
            # winning over the bare "အိုင်ဒီ".
            "my": ["ဂိမ်းအိုင်ဒီ", "ဂိမ်းအိုက်ဒီ", "ဂိမ်း ID", "အိုင်ဒီ"],
            "en": ["game id", "gameid", "gid", "player id"],
            "zh": ["游戏ID", "游戏账号ID"],
        },
        outputs={"en": "User ID", "my": "အသုံးပြုသူ ID", "zh": "用户ID"},
    ),
    ConceptSeed(
        key="user_account",
        approved=True,
        enabled=True,
        variants={
            "my": ["ဂိမ်းအကောင့်"],
            "en": ["game account", "gaming account", "player account"],
            "zh": ["游戏账号"],
        },
        outputs={"en": "User Account", "my": "အသုံးပြုသူ အကောင့်", "zh": "用户账户"},
    ),
    ConceptSeed(
        key="balance",
        approved=True,
        enabled=True,
        variants={
            "my": ["ဂိမ်းပွိုင့်", "ဂိမ်းအမှတ်", "ပွိုင့်"],
            "en": ["game points", "game point", "points", "chips", "coins"],
            "zh": ["游戏积分", "积分"],
        },
        # Owner choice 2026-09-19: "Amount" over the spec's "Balance / Credit / Funds".
        outputs={"en": "Amount", "my": "ပမာဏ", "zh": "金额"},
    ),
    ConceptSeed(
        key="platform",
        approved=True,
        enabled=True,
        variants={
            "my": ["ဂိမ်းထဲ", "ဂိမ်း"],
            "en": ["in-game", "ingame", "in game"],
            # Bare "游戏" is included: the spec's own few-shot example masks
            # "游戏里" as ⟦T:platform⟧. Longest-match-first keeps the longer
            # concepts (游戏积分, 游戏账号, 游戏ID) winning where they overlap.
            "zh": ["游戏内", "游戏"],
        },
        # Spec lists "Account / Platform / System" - renderer uses "Platform".
        outputs={"en": "Platform", "my": "ပလက်ဖောင်း", "zh": "平台"},
    ),
    ConceptSeed(
        key="member",
        # Approved and enabled by the owner 2026-09-19: player -> Customer.
        approved=True,
        enabled=True,
        variants={
            "my": ["ကစားသမား"],
            "en": ["player", "punter", "bettor"],
            "zh": ["玩家"],
        },
        outputs={"en": "Customer", "my": "ဖောက်သည်", "zh": "客户"},
    ),
]

# Deny lists are per OUTPUT language. Scanning an English output with
# Myanmar words finds nothing, so all three lists are maintained.
# DRAFT - an admin must review and approve these before go-live.
DENY_TERMS: dict[str, list[str]] = {
    "en": [
        "game", "games", "gaming", "gamer", "gamers",
        "casino", "casinos", "slot", "slots",
        "betting", "gamble", "gambling", "bettor",
        "bookmaker", "sportsbook",
    ],
    "my": [
        "ဂိမ်း",
        "ကာစီနို",
        "လောင်း",
        "လောင်းကစား",
        "စလော့",
    ],
    "zh": [
        "游戏",
        "赌场",
        "赌博",
        "博彩",
        "老虎机",
        "投注",
    ],
}

POLICY_VERSION_DEFAULT = 1
