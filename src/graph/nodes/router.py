"""Router + safety gate nodes (Topic Selector + Trust Layer equivalents).

Design lesson carried over from the production incident: crisis/self-harm intent
is checked FIRST, deterministically, and routed to escalation *before* any
generic content moderation can intercept it. In a managed platform you don't
control that ordering; here we do, and we make it explicit.
"""

from __future__ import annotations

import json

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
    """Classify intent via the LLM (skipped if the crisis gate already routed).

    Args:
        state: Current agent state.
        provider: LLM backend for classification.

    Returns:
        State with a resolved ``intent``.
    """
    if state.get("intent") is Intent.ESCALATION:
        return {}
    raw = provider.complete(_ROUTER_SYSTEM, state.get("user_input", ""), json_mode=True)
    try:
        intent = Intent(json.loads(raw).get("intent", "off_topic"))
    except (json.JSONDecodeError, ValueError):
        intent = Intent.OFF_TOPIC
    return {"intent": intent}


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
