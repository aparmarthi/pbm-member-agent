"""Terminal / small nodes: escalation, closing, off-topic, and order action.

Escalation and closing are fully implemented (safety-critical and trivial).
Order action is the channel-divergent capability shown in miniature (chat
deep-links; voice executes inline). Refill and drug price are now full nodes in
their own modules.
"""

from __future__ import annotations

from src.config.channels import for_channel
from src.graph.state import AgentState
from src.models.schemas import Channel

_HANDOFF = "live_agent"


def escalation(state: AgentState) -> AgentState:
    """Hand off to a human. Crisis-safe: always surfaces a warm transfer.

    For crisis-routed turns we lead with the crisis resource, then transfer —
    the behavior the managed platform failed to guarantee.

    Args:
        state: Current agent state.

    Returns:
        State marking the turn escalated with a handoff target.
    """
    text = (state.get("user_input") or "").lower()
    crisis = any(t in text for t in ("suicide", "kill myself", "self harm", "self-harm",
                                     "hurt myself", "end my life", "want to die", "overdose"))
    if crisis:
        reply = (
            "I'm really glad you told me. You don't have to go through this alone — "
            "you can reach the 988 Suicide & Crisis Lifeline any time by calling or texting 988. "
            "I'm connecting you with a Member Care Specialist right now."
        )
    else:
        reply = "I'll get a Member Care Specialist to help you with that."
    return {"escalated": True, "handoff_target": _HANDOFF, "messages": [("ai", reply)]}


def closing(state: AgentState) -> AgentState:
    """End-of-conversation acknowledgement (never force-ends the session).

    Args:
        state: Current agent state.

    Returns:
        State with a brief closing reply.
    """
    return {"messages": [("ai", "You're all set. I'm here whenever you need anything else.")]}


def off_topic(state: AgentState) -> AgentState:
    """Politely decline out-of-scope requests without answering them.

    Args:
        state: Current agent state.

    Returns:
        State with a redirect reply.
    """
    return {"messages": [(
        "ai",
        "I can help with prescription order status, refills, and drug pricing. "
        "What would you like to check?",
    )]}


def order_action(state: AgentState) -> AgentState:
    """Order action — channel-divergent stub (the portfolio thesis in miniature).

    Chat deep-links to the authenticated web CTA; voice would execute inline with
    confirmation + step-up auth. Full action logic lands in the next build pass.

    Args:
        state: Current agent state.

    Returns:
        State with a channel-appropriate placeholder reply.
    """
    channel = state.get("channel", Channel.CHAT)
    if for_channel(channel).actions_execute_inline:
        reply = ("[order_action:voice] I can take care of that on this call. First I'll need to "
                 "confirm a few details to verify your identity. (Inline execution stubbed.)")
    else:
        reply = ("[order_action:chat] You can take care of that securely on your account page — "
                 "here's the link. (Web deep-link stubbed.)")
    return {"messages": [("ai", reply)]}
