"""Crisis-language lexicon: the deterministic floor under crisis detection.

Patterns are grouped by the Columbia Suicide Severity Rating Scale (C-SSRS)
ideation categories, so the list grows by clinical category rather than by
patching eval misses. This is the first of two independent detectors: the LLM
router also returns a ``crisis`` flag, and either one can raise a crisis while
neither can clear one (ADR-012).

Idioms ("this price is killing me", "dying to get it") are deliberately not
matched; every pattern needs a first-person reference to self or to living.
"""

from __future__ import annotations

import re

_ME = r"my ?self"  # not "me": "this copay will kill me" is an idiom

CRISIS_PATTERNS: dict[str, tuple[str, ...]] = {
    "wish_to_be_dead": (
        r"\bwant(?:ed)? to (?:die|be dead)\b",
        r"\bwish (?:i was|i were|i'd|i could be) dead\b",
        r"\bwish i (?:was|were)n'?t (?:alive|here|born)\b",
        r"\b(?:don'?t|do not) want to (?:be alive|live|be here|exist|wake up)\b",
        r"\bbetter off (?:dead|without me)\b",
        r"\b(?:hope|wish|pray) i (?:don'?t|never) wake up\b",
    ),
    "active_ideation": (
        r"\bsuicid",
        rf"\bkill(?:ing)? {_ME}\b",
        r"\bend(?:ing)? (?:my (?:own )?life|it all)\b",
        r"\btake my (?:own )?life\b",
    ),
    "method_or_plan": (
        r"\boverdos",
        r"\btake (?:all|every one) of (?:my|the|these|those) (?:pills|meds|medications?)\b",
        r"\btake all (?:my|the|these|those) (?:pills|meds|medications?)\b",
        r"\bstockpil(?:e|ing) (?:my |the )?(?:pills|meds)\b",
        r"\benough (?:pills |meds )?to (?:not wake up|never wake up|die|end it)\b",
    ),
    "self_harm": (
        r"\bself[- ]?harm",
        rf"\b(?:hurt|hurting|harm|harming|cut|cutting) {_ME}\b",
    ),
    "hopelessness_about_living": (
        r"\bno (?:point|reason) (?:in |to )?(?:living|live|go(?:ing)? on|being alive)\b",
        r"\bcan'?t go on (?:living|anymore|like this)\b",
        r"\bno longer want to (?:live|be here)\b",
        r"\blife (?:isn'?t|is not) worth living\b",
    ),
}

_COMPILED = [re.compile(p) for group in CRISIS_PATTERNS.values() for p in group]


def detect_crisis(text: str) -> bool:
    """Return True if the utterance matches any crisis pattern.

    Args:
        text: Raw member utterance.

    Returns:
        Whether the deterministic lexicon flags crisis language.
    """
    normalized = re.sub(r"\s+", " ", text.lower().replace("’", "'"))
    return any(p.search(normalized) for p in _COMPILED)
