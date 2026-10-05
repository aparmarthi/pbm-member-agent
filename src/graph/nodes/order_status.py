"""Order Status node — the deep, production-depth read path.

Pipeline: fetch (grounding) → deterministic resolve+rank → channel-aware
paginate → render. The LLM is deliberately kept out of status *derivation*;
rendering is a deterministic template so output is faithful by construction
(the anti-hallucination lesson from the production agent's strict output
contract, implemented structurally rather than via prompt pleading).
"""

from __future__ import annotations

from src.config.channels import for_channel
from src.graph.state import AgentState
from src.graph.tools import fetch_orders, resolve_statuses
from src.models.schemas import Channel, ResolvedStatus

_NO_ORDERS_CHAT = (
    "I looked back {days} days and didn't find any active orders. A Member Care "
    "Specialist can help with additional questions — would you like me to connect you?"
)
_NO_ORDERS_VOICE = (
    "I checked your recent orders and didn't find any active ones. "
    "Would you like me to check whether any prescriptions are ready to refill?"
)


def order_status(state: AgentState) -> AgentState:
    """Resolve and present the member's order statuses for this turn.

    Args:
        state: Current agent state (must carry ``member`` and ``channel``).

    Returns:
        State updates: resolved statuses, pagination flag, reply text, and an
        escalation flag if any surfaced status mandates a human transfer.
    """
    member = state.get("member")
    channel = state.get("channel", Channel.CHAT)
    cfg = for_channel(channel)

    if member is None or not any(p.orders for p in member.patients):
        days = cfg.lookback_days
        reply = (_NO_ORDERS_CHAT if channel is Channel.CHAT else _NO_ORDERS_VOICE).format(days=days)
        return {"resolved": [], "has_more": False, "messages": [("ai", reply)]}

    member = fetch_orders(member)
    resolved = resolve_statuses(member, channel)

    if not resolved:
        reply = (_NO_ORDERS_CHAT if channel is Channel.CHAT else _NO_ORDERS_VOICE).format(
            days=cfg.lookback_days
        )
        return {"resolved": [], "has_more": False, "messages": [("ai", reply)]}

    page = resolved[: cfg.page_size]
    has_more = len(resolved) > cfg.page_size

    if any(s.escalate for s in page):
        reply = _render(page, channel, cfg.lookback_days, has_more, len(resolved))
        reply += "\n\nI'll connect you with a Member Care Specialist who can help."
        return {
            "resolved": resolved, "has_more": has_more, "escalated": True,
            "handoff_target": "live_agent", "messages": [("ai", reply)],
        }

    reply = _render(page, channel, cfg.lookback_days, has_more, len(resolved))
    return {"resolved": resolved, "has_more": has_more, "messages": [("ai", reply)]}


def _render(
    page: list[ResolvedStatus], channel: Channel, lookback: int, has_more: bool, total: int
) -> str:
    """Render statuses deterministically per channel conventions.

    Args:
        page: The statuses to show this turn.
        channel: Active channel (controls phrasing/pagination copy).
        lookback: Lookback window in days, stated to the member.
        has_more: Whether additional statuses remain.
        total: Total resolved statuses (for the count preheader).

    Returns:
        Member-facing reply string.
    """
    header = (
        f"Here's what I found from the last {lookback} days "
        f"({total} order{'s' if total != 1 else ''}):"
    )
    lines = []
    for s in page:
        cta = f" — {s.primary_cta}" if s.primary_cta else ""
        price = f" (${s.price:.2f})" if s.price is not None and s.self_serve else ""
        lines.append(f"• {s.patient_name} — {s.drug_name}: {s.status}. {s.sub_status}{price}{cta}")
    body = "\n".join(lines)

    footer = ""
    if has_more:
        remaining = total - len(page)
        if channel is Channel.VOICE:
            footer = f"\nThat's the first {len(page)}. Would you like to hear the other {remaining}?"
        else:
            footer = (
                f"\nI'm showing the {len(page)} most relevant orders. "
                f"There are {remaining} more if you'd like to see them."
            )
    else:
        footer = "\nCan I help you with anything else?"
    return f"{header}\n{body}{footer}"
