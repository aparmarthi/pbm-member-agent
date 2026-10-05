"""Order Status node — the deep, production-depth read path.

Pipeline: fetch (grounding) → deterministic resolve+rank (within the channel's
lookback window) → channel-aware paginate → render. The LLM is deliberately kept
out of status *derivation*; rendering is a deterministic template so output is
faithful by construction (the anti-hallucination lesson from the production
agent's strict output contract, implemented structurally rather than via prompt
pleading).

Every dead end ends on an offer the router can resolve next turn: "see the
rest", chat's 6-month search, a specialist, or (voice) a refill check.
"""

from __future__ import annotations

from src.config.channels import ChannelConfig, for_channel
from src.graph.state import AgentState
from src.graph.tools import fetch_orders, resolve_statuses
from src.models.schemas import Channel, Member, ResolvedStatus

_NO_ORDERS_CHAT = (
    "I looked back {window} and didn't find any active orders. A Member Care "
    "Specialist can help with additional questions — would you like me to connect you?"
)
_NO_ORDERS_EXTENDED_OFFER = (
    "I looked back {window} and didn't find any active orders. "
    "Would you like me to check the last {extended}?"
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
        State updates: resolved statuses, window, page, reply text, the offer
        made (if any), and an escalation flag if any surfaced status mandates a
        human transfer.
    """
    member = state.get("member")
    channel = state.get("channel", Channel.CHAT)
    cfg = for_channel(channel)
    followup = state.get("followup")
    page = state.get("page", 1)

    if followup == "more_orders" and state.get("resolved"):
        resolved = state["resolved"]
        days = state.get("lookback_days", cfg.lookback_days)
    else:
        page = 1
        days = cfg.extended_lookback_days if followup == "extended_lookback" else cfg.lookback_days
        resolved = resolve_statuses(fetch_orders(member), channel, lookback_days=days) if member else []

    if not resolved:
        return _no_orders(member, channel, cfg, days)

    start = (page - 1) * cfg.page_size
    shown = resolved[start:start + cfg.page_size]
    remaining = len(resolved) - start - len(shown)
    escalate = any(s.escalate for s in shown)
    update: AgentState = {
        "resolved": resolved, "has_more": remaining > 0, "lookback_days": days, "page": page,
        "messages": [("ai", _render(shown, channel, days, len(resolved), page, remaining, escalate))],
    }
    if escalate:
        update.update(escalated=True, handoff_target="live_agent")
    elif remaining:
        update["offer"] = "more_orders"
    return update


def _no_orders(member: Member | None, channel: Channel, cfg: ChannelConfig, days: int) -> AgentState:
    """Reply when the window is empty, always ending on a next-step offer.

    Args:
        member: The session member, if any.
        channel: Active channel.
        cfg: Channel config.
        days: The window that was just searched.

    Returns:
        State updates with the reply and the offer it makes.
    """
    update: AgentState = {"resolved": [], "has_more": False, "lookback_days": days}
    if channel is Channel.VOICE:
        return {**update, "offer": "check_refill", "messages": [("ai", _NO_ORDERS_VOICE)]}

    extended = cfg.extended_lookback_days
    if extended and days < extended and member is not None and resolve_statuses(
        member, channel, lookback_days=extended
    ):
        reply = _NO_ORDERS_EXTENDED_OFFER.format(window=_window(days), extended=_window(extended))
        return {**update, "offer": "extended_lookback", "messages": [("ai", reply)]}
    reply = _NO_ORDERS_CHAT.format(window=_window(days))
    return {**update, "offer": "connect_agent", "messages": [("ai", reply)]}


def _window(days: int) -> str:
    """Member-facing name for a lookback window ("45 days", "6 months")."""
    return f"{days // 30} months" if days >= 180 else f"{days} days"


def _render(
    shown: list[ResolvedStatus],
    channel: Channel,
    lookback: int,
    total: int,
    page: int,
    remaining: int,
    escalate: bool,
) -> str:
    """Render one page of statuses deterministically per channel conventions.

    Args:
        shown: The statuses to show this turn.
        channel: Active channel (controls phrasing/pagination copy).
        lookback: Lookback window in days, stated to the member.
        total: Total resolved statuses (for the count preheader).
        page: 1-based page being shown.
        remaining: Statuses left after this page.
        escalate: Whether a shown status forces a transfer (replaces the footer).

    Returns:
        Member-facing reply string.
    """
    if page == 1:
        header = (f"Here's what I found from the last {_window(lookback)} "
                  f"({total} order{'s' if total != 1 else ''}):")
    else:
        header = "Here's the other one:" if len(shown) == 1 else f"Here are the next {len(shown)}:"
    lines = []
    for s in shown:
        cta = f" — {s.primary_cta}" if s.primary_cta else ""
        price = f" (${s.price:.2f})" if s.price is not None and s.self_serve else ""
        lines.append(f"• {s.patient_name} — {s.drug_name}: {s.status}. {s.sub_status}{price}{cta}")
    body = "\n".join(lines)

    if escalate:
        footer = "\nI'll connect you with a Member Care Specialist who can help with this."
    elif remaining and channel is Channel.VOICE:
        footer = f"\nWould you like to hear the other {'one' if remaining == 1 else remaining}?"
    elif remaining:
        lead = f"I'm showing the {len(shown)} most relevant orders. " if page == 1 else ""
        more = ("is 1 more order if you'd like to see it" if remaining == 1
                else f"are {remaining} more if you'd like to see them")
        footer = f"\n{lead}There {more}."
    else:
        footer = "\nCan I help you with anything else?"
    return f"{header}\n{body}{footer}"
