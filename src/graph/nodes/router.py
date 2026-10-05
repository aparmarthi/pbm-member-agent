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

from src.config.crisis import detect_crisis
from src.graph.state import AgentState
from src.models.schemas import Intent
from src.utils.llm import LLMProvider

_ROUTER_SYSTEM = (
    "You are the intent router for a pharmacy benefits member-service agent. "
    "Classify the member's message into exactly one intent and reply with a JSON "
    "object {\"intent\": \"...\", \"crisis\": true|false}. Valid intents: order_status, order_action, "
    "refill, drug_price, escalation, closing, off_topic. Route to escalation for "
    "any request for a human/agent/representative or any expression of high "
    "frustration. Route order_status for questions about where an order/"
    "prescription is or its delivery. Set crisis to true if the message expresses, "
    "even indirectly, a wish to die, suicidal thoughts, self-harm, a plan to "
    "overdose, or hopelessness about living; idioms like 'this price is killing "
    "me' are not a crisis. Return only the JSON object."
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
    return {"intent": None, "escalated": False, "handoff_target": None, "followup": None,
            "crisis": False}


def crisis_gate(state: AgentState) -> AgentState:
    """Force-route self-harm/crisis input to escalation, deterministically.

    Args:
        state: Current agent state.

    Returns:
        State with intent pinned to ESCALATION and ``crisis`` set when the
        lexicon matches; otherwise unchanged.
    """
    if detect_crisis(state.get("user_input") or ""):
        return {"intent": Intent.ESCALATION, "crisis": True}
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

    intent, crisis = _classify(state.get("user_input", ""), provider)
    # The LLM is a second crisis detector: it can raise a crisis, never clear one.
    if crisis:
        return {**update, "intent": Intent.ESCALATION, "crisis": True}
    # "Which medication?" → a bare drug name classifies as off-topic; it isn't.
    if offer == "drug_name" and intent is Intent.OFF_TOPIC:
        intent = Intent.DRUG_PRICE
    return {**update, "intent": intent}


def _classify(text: str, provider: LLMProvider) -> tuple[Intent, bool]:
    """Ask the LLM for an intent and crisis flag; off-topic, no crisis on bad output."""
    raw = provider.complete(_ROUTER_SYSTEM, text, json_mode=True)
    try:
        parsed = json.loads(raw)
        return Intent(parsed.get("intent", "off_topic")), parsed.get("crisis") is True
    except (json.JSONDecodeError, ValueError, AttributeError):
        return Intent.OFF_TOPIC, False


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
