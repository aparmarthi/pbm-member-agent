"""Drug price node — real implementation with coverage, PA, and alternatives.

Extracts the drug name from the utterance, runs a deterministic benefit lookup,
and handles the three coverage outcomes from the pricing stories: not-covered
(offer generic alternatives), prior-auth-required (explain + offer cost), and a
covered price. The agent never recommends a drug for a condition (TLPDMSF-338).
"""

from __future__ import annotations

import re

from src.graph.state import AgentState
from src.graph.tools import price_drug

# Known drug tokens for extraction from free-text utterances.
_KNOWN_DRUGS = (
    "wegovy", "zepbound", "saxenda", "vyvanse", "adderall", "abilify",
    "lipitor", "atorvastatin", "synthroid", "levothyroxine", "metformin",
    "januvia", "pepcid", "lisinopril", "topamax", "brilinta", "nexium",
    "losartan", "omeprazole", "jardiance", "skyrizi",
)


def _extract_drug(text: str, explicit: str | None) -> str | None:
    """Extract a drug name from state or the utterance.

    Args:
        text: The raw user utterance.
        explicit: A drug name already captured in state, if any.

    Returns:
        A drug name, or None if none could be identified.
    """
    if explicit:
        return explicit
    lowered = text.lower()
    for drug in _KNOWN_DRUGS:
        if re.search(rf"\b{re.escape(drug)}\b", lowered):
            return drug
    return None


def drug_price(state: AgentState) -> AgentState:
    """Answer a drug price / coverage question for the requested medication.

    Args:
        state: Current agent state.

    Returns:
        State updates: a resolved :class:`PriceQuote` and a member-facing reply,
        or a disambiguation prompt when no drug could be identified.
    """
    text = state.get("user_input", "")
    drug = _extract_drug(text, state.get("drug_query"))
    if not drug:
        return {"messages": [(
            "ai", "I can check what a medication costs under your plan. "
                  "Which medication would you like me to look up?",
        )]}

    quote = price_drug(drug)
    reply = quote.message
    if quote.alternatives:
        alts = ", ".join(a.title() for a in quote.alternatives)
        reply += f" A lower-cost option may be available: {alts}. " \
                 "Talk with your prescriber about whether it's right for you."
    return {"price_quote": quote, "drug_query": drug, "messages": [("ai", reply)]}
