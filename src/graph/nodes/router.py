"""Router + safety gate nodes (Topic Selector + Trust Layer equivalents).

Design lesson carried over from the production incident: crisis/self-harm intent
is checked FIRST, deterministically, and routed to escalation *before* any
generic content moderation can intercept it. In a managed platform you don't
control that ordering; here we do, and we make it explicit.

Multi-turn: when the previous turn ended on a yes/no offer ("want to see the
rest?"), the router resolves the reply deterministically instead of asking the
LLM — "yes" has no intent on its own; it only means something given the offer.
"""

from __future__ import annotations

import json
import re

from src.graph.state import AgentState
from src.models.schemas import Intent
from src.utils.llm import LLMProvider

# Deterministic crisis triggers — never left to a classifier's discretion.
_CRISIS_TERMS = (
    "suicide", "kill myself", "self harm", "self-harm", "hurt myself",
    "end my life", "want to die", "overdose",
)

_ROUTER_SYSTEM = (
    "You are the intent router for a pharmacy benefits member-service agent. "
    "Classify the member's message into exactly one intent and reply with a JSON "
    "object {\"intent\": \"...\"}. Valid intents: order_status, order_action, "
    "refill, drug_price, escalation, closing, off_topic. Route to escalation for "
    "any request for a human/agent/representative or any expression of high "
    "frustration. Route order_status for questions about where an order/"
    "prescription is or its delivery. Return only the JSON object."
)


# Offer the agent made last turn → the intent that accepting it maps to.
_OFFER_INTENTS = {
    "more_orders": Intent.ORDER_STATUS,
    "more_refills": Intent.REFILL,
    "extended_lookback": Intent.ORDER_STATUS,
    "connect_agent": Intent.ESCALATION,
    "check_refill": Intent.REFILL,
    "pa_cost": Intent.DRUG_PRICE,
    "add_to_cart": Intent.ORDER_ACTION,
}
_PAGED_OFFERS = {"more_orders", "more_refills"}
_YES = re.compile(r"^(yes|yeah|yep|yup|sure|ok|okay|please|go ahead)\b")
_NO = re.compile(r"^(no|nope|nah|not now)\b")
_MORE = ("more", "the rest", "the other", "next")


def begin_turn(state: AgentState) -> AgentState:
    """Clear per-turn decisions so nothing leaks in from the previous turn.

    Args:
        state: Current agent state (carries the prior turn when checkpointed).

    Returns:
        Resets for the fields each turn decides afresh.
    """
    return {"intent": None, "escalated": False, "handoff_target": None, "followup": None}


def crisis_gate(state: AgentState) -> AgentState:
    """Force-route self-harm/crisis input to escalation, deterministically.

    Args:
        state: Current agent state.

    Returns:
        State with intent pinned to ESCALATION when a crisis term is present;
        otherwise unchanged.
    """
    text = (state.get("user_input") or "").lower()
    if any(term in text for term in _CRISIS_TERMS):
        return {"intent": Intent.ESCALATION}
    return {}


def route(state: AgentState, provider: LLMProvider) -> AgentState:
    """Resolve this turn's intent.

    Order of precedence: crisis gate (already set) → pending authentication →
    reply to last turn's offer → LLM classification.

    Args:
        state: Current agent state.
        provider: LLM backend for classification.

    Returns:
        State with a resolved ``intent``, the consumed ``offer`` cleared, and
        ``page``/``followup`` set when the member accepted an offer.
    """
    update: AgentState = {"offer": None, "page": 1}
    if state.get("intent") is Intent.ESCALATION:
        return update

    # Mid-authentication the utterance is an identity token or DOB: resume the
    # pending request and keep it away from the LLM.
    auth = state.get("auth")
    if auth and auth.pending_intent:
        return {**update, "intent": Intent(auth.pending_intent)}

    text = re.sub(r"[^\w\s']", "", (state.get("user_input") or "").lower()).strip()
    offer = state.get("offer")
    if offer in _OFFER_INTENTS:
        if _NO.match(text):
            return {**update, "intent": Intent.CLOSING}
        if _YES.match(text) or (offer in _PAGED_OFFERS and any(m in text for m in _MORE)):
            page = state.get("page", 1) + 1 if offer in _PAGED_OFFERS else 1
            return {"offer": None, "page": page, "intent": _OFFER_INTENTS[offer],
                    "followup": offer}

    intent = _classify(state.get("user_input", ""), provider)
    # "Which medication?" → a bare drug name classifies as off-topic; it isn't.
    if offer == "drug_name" and intent is Intent.OFF_TOPIC:
        intent = Intent.DRUG_PRICE
    return {**update, "intent": intent}


def _classify(text: str, provider: LLMProvider) -> Intent:
    """Ask the LLM for an intent, falling back to off-topic on bad output."""
    raw = provider.complete(_ROUTER_SYSTEM, text, json_mode=True)
    try:
        return Intent(json.loads(raw).get("intent", "off_topic"))
    except (json.JSONDecodeError, ValueError, AttributeError):
        return Intent.OFF_TOPIC


def route_selector(state: AgentState) -> str:
    """Conditional-edge selector mapping intent to the next node name.

    Args:
        state: Current agent state.

    Returns:
        The name of the node to transition to.
    """
    intent = state.get("intent") or Intent.OFF_TOPIC
    return {
        Intent.ORDER_STATUS: "order_status",
        Intent.ORDER_ACTION: "order_action",
        Intent.REFILL: "refill",
        Intent.DRUG_PRICE: "drug_price",
        Intent.ESCALATION: "escalation",
        Intent.CLOSING: "closing",
        Intent.OFF_TOPIC: "off_topic",
    }[intent]
