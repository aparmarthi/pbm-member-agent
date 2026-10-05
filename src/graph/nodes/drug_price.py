"""Drug price node — real implementation with coverage, PA, and alternatives.

Extracts the drug name from the utterance, runs a deterministic benefit lookup,
and handles the three coverage outcomes from the pricing stories: not-covered
(offer generic alternatives), prior-auth-required (explain + offer cost), and a
covered price. The agent never recommends a drug for a condition.
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


def _extract_drug(text: str) -> str | None:
    """Extract a known drug name from the utterance.

    Args:
        text: The raw user utterance.

    Returns:
        A drug name, or None if none could be identified.
    """
    lowered = text.lower()
    for drug in _KNOWN_DRUGS:
        if re.search(rf"\b{re.escape(drug)}\b", lowered):
            return drug
    return None


def drug_price(state: AgentState) -> AgentState:
    """Answer a drug price / coverage question for the requested medication.

    The drug comes from this turn's utterance; the stored ``drug_query`` is only
    used when the member accepts last turn's "hear the estimated cost?" offer.

    Args:
        state: Current agent state.

    Returns:
        State updates: a resolved :class:`PriceQuote` and a member-facing reply,
        or a disambiguation prompt when no drug could be identified.
    """
    if state.get("followup") == "pa_cost" and state.get("price_quote"):
        quote = state["price_quote"]
        return {"messages": [(
            "ai", f"Once the prior authorization is approved, the estimated cost of "
                  f"{quote.drug_name} is ${quote.price:.2f}. Can I help with anything else?",
        )]}

    drug = _extract_drug(state.get("user_input", ""))
    if not drug:
        return {"offer": "drug_name", "messages": [(
            "ai", "I can check what a medication costs under your plan. "
                  "Which medication would you like me to look up?",
        )]}

    quote = price_drug(drug.title())
    reply = quote.message
    if quote.alternatives:
        alts = ", ".join(a.title() for a in quote.alternatives)
        reply += f" A lower-cost option may be available: {alts}. " \
                 "Talk with your prescriber about whether it's right for you."
    update: AgentState = {"price_quote": quote, "drug_query": drug, "messages": [("ai", reply)]}
    if quote.prior_auth_required:
        update["offer"] = "pa_cost"
    return update
