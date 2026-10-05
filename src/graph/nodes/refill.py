"""Refill node — real implementation over the condition-code truth table.

Presents refillable prescriptions in priority order, states cost when available,
offers to add eligible Rxs to the cart, and handles the non-refillable outcomes
(too early, too old, controlled, not available, renewal, transfer) with the
exact member messaging from the refill stories. Transfer-outcome codes escalate.
"""

from __future__ import annotations

from src.config.channels import for_channel
from src.graph.state import AgentState
from src.graph.tools import check_refill_eligibility
from src.models.schemas import Channel, RefillCandidate

_NO_RX = ("I don't see any prescriptions on the account to refill. "
          "Is there something else I can help you with?")


def refill(state: AgentState) -> AgentState:
    """Evaluate and present refill options for the member's prescriptions.

    Args:
        state: Current agent state (must carry ``member`` and ``channel``).

    Returns:
        State updates: refill candidates, a member-facing reply, and an
        escalation flag when a transfer-outcome code is present.
    """
    member = state.get("member")
    channel = state.get("channel", Channel.CHAT)
    if member is None or not any(p.orders for p in member.patients):
        return {"refill_candidates": [], "messages": [("ai", _NO_RX)]}

    candidates = check_refill_eligibility(member)
    listable = [c for c in candidates if c.list_priority is not None]
    must_transfer = [c for c in candidates if c.transfer]

    if must_transfer:
        reply = (f"I'll connect you with a Member Care Specialist to help with "
                 f"{must_transfer[0].drug_name}.")
        return {"refill_candidates": candidates, "escalated": True,
                "handoff_target": "live_agent", "messages": [("ai", reply)]}

    if not listable:
        # Nothing refillable, but explain the top blocking reason and pivot.
        blocking = candidates[0] if candidates else None
        reply = (blocking.message + " Is there anything else I can help with?"
                 if blocking else _NO_RX)
        return {"refill_candidates": candidates, "messages": [("ai", reply)]}

    page = state.get("page", 1) if state.get("followup") == "more_refills" else 1
    reply, remaining = _render(listable, channel, page)
    return {"refill_candidates": candidates, "page": page,
            "offer": "more_refills" if remaining else "add_to_cart",
            "messages": [("ai", reply)]}


def _render(listable: list[RefillCandidate], channel: Channel, page: int) -> tuple[str, int]:
    """Render one page of the refillable-prescription list per channel.

    Args:
        listable: Refillable candidates, pre-sorted by list priority.
        channel: Active channel (controls pagination copy).
        page: 1-based page to show.

    Returns:
        The member-facing reply and how many candidates remain after this page.
    """
    page_size = for_channel(channel).page_size
    start = (page - 1) * page_size
    shown = listable[start:start + page_size]
    remaining = len(listable) - start - len(shown)
    lines = []
    for c in shown:
        cost = f" — estimated ${c.price:.2f}" if c.price is not None else ""
        note = "" if c.outcome == "ready" else f" ({c.message})"
        lines.append(f"• {c.drug_name}{cost}{note}")
    n = len(shown)
    if page == 1:
        header = f"Here {'is' if n == 1 else 'are'} {n} prescription{'' if n == 1 else 's'} you can order:"
    else:
        header = "Here's the other one:" if n == 1 else f"Here are the next {n}:"
    if remaining and channel is Channel.VOICE:
        footer = f"\nWould you like to hear the other {'one' if remaining == 1 else remaining}?"
    elif remaining:
        footer = f"\nShowing {start + n} of {len(listable)}. Want to see the rest?"
    else:
        footer = f"\nWould you like to add {'it' if n == 1 else 'any of these'} to your order?"
    return f"{header}\n" + "\n".join(lines) + footer, remaining
