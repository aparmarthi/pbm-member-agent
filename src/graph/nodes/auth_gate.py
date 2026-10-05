"""Authentication gate — step-up before any PHI-exposing intent.

Runs after routing and before PHI intents (order_status, order_action, refill,
drug_price). If the session hasn't reached Level 1.5, the gate parks the request,
collects a primary token (member ID or Rx number) and then DOB across turns, and
replays the original request once verified. A member with a privacy flag is
transferred after auth. This is the deterministic auth model from the auth
stories — the LLM never adjudicates identity.
"""

from __future__ import annotations

from dataclasses import replace

from src.config.auth import (
    MAX_TOKEN_ATTEMPTS,
    PHI_INTENTS,
    AuthLevel,
    AuthState,
    dob_matches,
    match_token,
    register_dob_attempt,
    requires_step_up,
    route_caller_type,
)
from src.graph.state import AgentState
from src.models.schemas import Intent

# Prompts differ by intent (refill asks Rx first; others ask ID).
_REFILL_PROMPT = ("I can help with that — let me look up the account. "
                  "If you have the prescription number, you can give me that.")
_OTHER_PROMPT = ("Let me look up the account. Do you have the member ID for you "
                 "or the person you're calling about?")
_TOKEN_REPROMPT = ("I couldn't find an account with that. Could you give me the member ID "
                   "or a prescription number again?")
_DOB_PROMPT = "Thanks. To verify, what's the date of birth of the person you're calling about?"
_DOB_REPROMPT = ("That date of birth doesn't match our records. Could you say it once more, "
                 "with the month, day, and year?")
_VERIFY_FAILED = ("I wasn't able to verify the account, so I'll connect you with a "
                  "Member Care Specialist who can help.")
_PRIVACY_TRANSFER = ("For your security, I'll connect you with a Member Care Specialist "
                     "to help with that.")


def auth_gate(state: AgentState) -> AgentState:
    """Enforce step-up authentication for PHI intents.

    A session started with ``is_verified=True`` is treated as having reached
    Level 1.5 (chat sessions are authenticated by the web login). Otherwise the
    gate parks the PHI request and collects credentials over the next turns.

    Args:
        state: Current agent state.

    Returns:
        State updates: the session :class:`AuthState`, plus either a credential
        prompt (pending auth), a transfer, or — once verified — the original
        request restored into ``user_input`` so the intent node can answer it.
    """
    intent = state.get("intent")
    auth = replace(state.get("auth") or AuthState())

    # Non-member callers never reach member self-service.
    if route_caller_type(auth.caller_type) != "member_flow":
        return _transfer(auth, route_caller_type(auth.caller_type),
                         "I'll route you to the right team for that.")

    # Escalation (crisis or "get me a human") never waits on credentials.
    if intent is Intent.ESCALATION:
        auth.pending_intent = auth.pending_input = None
        return {"auth": auth}

    # Session-level verification shortcut (CLI/API injects a verified member).
    if state.get("is_verified"):
        auth.level = AuthLevel.LEVEL_1_5
        auth.token_verified = True

    if auth.pending_intent and auth.level is not AuthLevel.LEVEL_1_5:
        return _collect_credentials(state, auth)

    if intent is None or intent.value not in PHI_INTENTS:
        return {"auth": auth}

    if not requires_step_up(intent.value, auth.level):
        # Privacy-flagged members are helped only via a human after authentication.
        if auth.privacy_flag:
            return _transfer(auth, "live_agent", _PRIVACY_TRANSFER)
        return {"auth": auth}

    auth.pending_intent = intent.value
    auth.pending_input = state.get("user_input")
    auth.step = "token"
    prompt = _REFILL_PROMPT if intent is Intent.REFILL else _OTHER_PROMPT
    return _pause(auth, prompt)


def _collect_credentials(state: AgentState, auth: AuthState) -> AgentState:
    """Consume one credential utterance: primary token first, then DOB.

    Args:
        state: Current agent state (``user_input`` holds the credential).
        auth: Copy of the session auth state to advance.

    Returns:
        A pause with the next prompt, a transfer, or — on success — the restored
        original request so the graph proceeds to the parked intent.
    """
    member = state.get("member")
    text = state.get("user_input") or ""

    if auth.step == "token":
        if member is not None and match_token(text, member):
            auth.token_verified = True
            auth.step = "dob"
            return _pause(auth, _DOB_PROMPT)
        auth.token_attempts += 1
        if auth.token_attempts >= MAX_TOKEN_ATTEMPTS:
            return _transfer(auth, "live_agent", _VERIFY_FAILED)
        return _pause(auth, _TOKEN_REPROMPT)

    action = register_dob_attempt(auth, member is not None and dob_matches(text, member))
    if action == "reprompt":
        return _pause(auth, _DOB_REPROMPT)
    if action != "verified":
        return _transfer(auth, "live_agent", _VERIFY_FAILED)

    auth.level = AuthLevel.LEVEL_1_5
    original = auth.pending_input or ""
    auth.pending_intent = auth.pending_input = None
    if auth.privacy_flag:
        return _transfer(auth, "live_agent", _PRIVACY_TRANSFER)
    return {"auth": auth, "user_input": original}


def _pause(auth: AuthState, prompt: str) -> AgentState:
    """End the turn on a credential prompt, keeping the request parked."""
    return {"auth": auth, "handoff_target": "pending_auth", "messages": [("ai", prompt)]}


def _transfer(auth: AuthState, target: str, message: str) -> AgentState:
    """End the turn with a handoff, abandoning any parked request."""
    auth.pending_intent = auth.pending_input = None
    return {"auth": auth, "escalated": True, "handoff_target": target,
            "messages": [("ai", message)]}


def auth_selector(state: AgentState) -> str:
    """Selector deciding whether to proceed to the intent node or end the turn.

    Args:
        state: Current agent state.

    Returns:
        ``"stop"`` when the gate paused for a credential or transferred,
        else ``"proceed"``.
    """
    if state.get("handoff_target") == "pending_auth" or state.get("escalated"):
        return "stop"
    return "proceed"
