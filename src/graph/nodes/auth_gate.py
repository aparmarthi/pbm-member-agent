"""Authentication gate — step-up before any PHI-exposing intent.

Runs after routing and before PHI intents (order_status, order_action, refill,
drug_price). If the session hasn't reached Level 1.5, the gate asks for a
primary token; a member with a privacy flag is transferred after auth. This is
the deterministic auth model from the auth stories — the LLM never adjudicates
identity.
"""

from __future__ import annotations

from src.config.auth import AuthLevel, AuthState, requires_step_up, route_caller_type
from src.graph.state import AgentState
from src.models.schemas import Intent

# Prompts differ by intent per TLPDMSF-393 (refill asks Rx first; others ask ID).
_REFILL_PROMPT = ("I can help with that — let me look up the account. "
                  "If you have the prescription number, you can give me that.")
_OTHER_PROMPT = ("Let me look up the account. Do you have the member ID for you "
                 "or the person you're calling about?")


def auth_gate(state: AgentState) -> AgentState:
    """Enforce step-up authentication for PHI intents.

    In this build, a session started with ``is_verified=True`` is treated as
    having reached Level 1.5 (the harness/CLI injects a verified member). When
    not verified, the gate emits the correct token prompt and marks the turn as
    needing auth so the graph can pause for input.

    Args:
        state: Current agent state.

    Returns:
        State updates: an initialized :class:`AuthState`, and — when step-up is
        needed — a token-collection prompt plus a pending-auth marker.
    """
    intent = state.get("intent")
    auth = state.get("auth") or AuthState()

    # Non-member callers never reach member self-service.
    if route_caller_type(auth.caller_type) != "member_flow":
        target = route_caller_type(auth.caller_type)
        return {"auth": auth, "escalated": True, "handoff_target": target,
                "messages": [("ai", "I'll route you to the right team for that.")]}

    # Session-level verification shortcut (CLI/API injects a verified member).
    if state.get("is_verified"):
        auth.level = AuthLevel.LEVEL_1_5
        auth.token_verified = True

    if intent is None or not requires_step_up(intent.value, auth.level):
        return {"auth": auth}

    # Privacy-flagged members are helped only via a human after authentication.
    if auth.privacy_flag:
        return {"auth": auth, "escalated": True, "handoff_target": "live_agent",
                "messages": [("ai", "For your security, I'll connect you with a "
                                     "Member Care Specialist to help with that.")]}

    prompt = _REFILL_PROMPT if intent is Intent.REFILL else _OTHER_PROMPT
    return {"auth": auth, "handoff_target": "pending_auth", "messages": [("ai", prompt)]}


def auth_selector(state: AgentState) -> str:
    """Selector deciding whether to proceed to the intent node or pause for auth.

    Args:
        state: Current agent state.

    Returns:
        ``"pending_auth"`` when a token prompt was emitted, else ``"proceed"``.
    """
    return "pending_auth" if state.get("handoff_target") == "pending_auth" else "proceed"
