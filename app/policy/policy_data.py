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
        key="regular_customer",
        approved=True,
        enabled=True,
        variants={
            "my": [
                "ပုံမှန်ကစားနေကျ fan", "ပုံမှန်ဆော့နေကျ fan",
                "ကစားနေကျ fan", "ဆော့နေကျ fan",
                "ပုံမှန်ကစားနေကျ", "ပုံမှန်ဆော့နေကျ",
                "ကစားနေကျ", "ဆော့နေကျ",
                "ပုံမှန် customer", "ပုံမှန် fan",
            ],
            "en": [
                "regular playing fan", "playing fan",
                "regular player", "regular gamer",
                "frequent player", "regular customer",
            ],
            "zh": ["老玩家", "经常玩的玩家", "常客"],
        },
        outputs={"en": "regular customer", "my": "ပုံမှန် Customer", "zh": "常客"},
    ),
    ConceptSeed(
        key="activity",
        approved=True,
        enabled=True,
        variants={
            "my": [
                "ကစားနေတယ်", "ဆော့နေတယ်",
                "ကစားနေသည်", "ဆော့နေသည်",
                "ကစားတာ", "ဆော့တာ",
                "ကစားခြင်း", "ဆော့ခြင်း",
            ],
            "en": ["playing games", "playing"],
            "zh": ["在玩", "玩游戏", "打游戏"],
        },
        outputs={"en": "active", "my": "အသုံးပြုနေတယ်", "zh": "活跃"},
    ),
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
            "my": ["ဂိမ်းပွိုင့်", "ဂိမ်းအမှတ်", "ပွိုင့်များ", "ပွိုင့်"],
            "en": ["game points", "game point", "points", "chips", "coins"],
            "zh": ["游戏积分", "积分"],
        },
        outputs={"en": "Amount", "my": "ပမာဏ", "zh": "金额"},
    ),
    ConceptSeed(
        key="platform",
        approved=True,
        enabled=True,
        variants={
            "my": ["ဂိမ်းထဲ", "ဂိမ်း"],
            "en": ["in-game", "ingame", "in game"],
            "zh": ["游戏内", "游戏"],
        },
        outputs={"en": "Platform", "my": "ပလက်ဖောင်း", "zh": "平台"},
    ),
    ConceptSeed(
        key="member",
        approved=True,
        enabled=True,
        variants={
            "my": ["ကစားသမားများ", "ကစားသမား", "ကစားသူများ", "ကစားသူ", "ကစားဖော်"],
            "en": ["player", "players", "punter", "bettor", "fan", "fans"],
            "zh": ["玩家"],
        },
        outputs={"en": "Customer", "my": "ဖောက်သည်", "zh": "客户"},
    ),
]

# Deny lists are per OUTPUT language.
DENY_TERMS: dict[str, list[str]] = {
    "en": [
        "game", "games", "gaming", "gamer", "gamers",
        "playing", "played", "player", "players",
        "playing fan", "fan", "fans",
        "casino", "casinos", "slot", "slots",
        "betting", "gamble", "gambling", "bettor",
        "bookmaker", "sportsbook",
    ],
    "my": [
        "ဂိမ်း",
        "ကစားသမား",
        "ကစားသူ",
        "ကစားနေကျ",
        "ဆော့နေကျ",
        "ကစား",
        "ဆော့",
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
