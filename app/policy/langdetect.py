"""Lightweight language detection via Unicode script-block counting.

No model downloads. Returns one of "my" | "en" | "auto", plus the
detected out-of-scope language name when the detector is confident the
input is outside MY - EN (e.g. "Thai", "Chinese").

Rule (spec v3.1, Gate 6): if confidence < 0.60, or the text is
mixed-language (no script dominates), do NOT reject - return "auto" and
let the provider handle it. UNSUPPORTED_LANG is only sent on a confident
out-of-scope detection.
"""
from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.60


def script_of(ch: str) -> str:
    o = ord(ch)
    if 0x1000 <= o <= 0x109F:
        return "myanmar"
    if 0x4E00 <= o <= 0x9FFF:
        return "cjk"  # treated as Chinese for this product
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
        return "latin"
    if 0x0E00 <= o <= 0x0E7F:
        return "thai"
    if 0xAC00 <= o <= 0xD7AF:
        return "hangul"
    if 0x3040 <= o <= 0x30FF:
        return "kana"
    if 0x0600 <= o <= 0x06FF:
        return "arabic"
    if 0x0400 <= o <= 0x04FF:
        return "cyrillic"
    if 0x0900 <= o <= 0x097F:
        return "devanagari"
    return "other"


_IN_SCOPE = {"myanmar": "my", "latin": "en"}

_OUT_OF_SCOPE_NAMES = {
    "cjk": "Chinese",
    "thai": "Thai",
    "hangul": "Korean",
    "kana": "Japanese",
    "arabic": "Arabic",
    "cyrillic": "Russian",
    "devanagari": "Hindi",
}


def detect(text: str) -> tuple[str, float, str | None]:
    """Detect the language of *text*.

    Returns (src, confidence, out_of_scope_name):
      - src is "my" | "en" | "auto".
      - out_of_scope_name is set only when the detector is confident the
        language is outside MY - EN - ZH (e.g. "Thai").
    """
    counts: dict[str, int] = {}
    total = 0
    for ch in text:
        s = script_of(ch)
        if s == "other":
            continue
        counts[s] = counts.get(s, 0) + 1
        total += 1

    if total == 0:
        # No letters at all (numbers, emoji, punctuation) - let it through.
        return "auto", 0.0, None

    top = max(counts, key=lambda k: counts[k])
    confidence = counts[top] / total

    if confidence < CONFIDENCE_THRESHOLD:
        return "auto", confidence, None

    if top in _IN_SCOPE:
        return _IN_SCOPE[top], confidence, None

    return "auto", confidence, _OUT_OF_SCOPE_NAMES.get(top, top.capitalize())
