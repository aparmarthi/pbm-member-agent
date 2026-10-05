"""Channel-aware configuration — the core "same brain, different hands" thesis.

Chat and voice share one agent graph but diverge on lookback window, pagination,
and how order actions are fulfilled (web deep-link vs. in-conversation execute).
Encoding the divergence as data (not branching prose) keeps it testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import Channel


@dataclass(frozen=True)
class ChannelConfig:
    """Per-channel behavior parameters.

    Attributes:
        lookback_days: Primary order-history window.
        future_fill_lookback_days: Extended window for future-fill statuses.
        extended_lookback_days: Secondary window offered when nothing is found
            (chat offers 6 months; voice has no extended offer in MVP).
        page_size: How many statuses to present at once.
        suppress_faststart: Whether FastStart statuses are hidden (voice=True).
        actions_execute_inline: True (voice) executes actions in-conversation;
            False (chat) deep-links to the authenticated web CTA.
    """

    lookback_days: int
    future_fill_lookback_days: int
    extended_lookback_days: int | None
    page_size: int
    suppress_faststart: bool
    actions_execute_inline: bool


_CONFIG: dict[Channel, ChannelConfig] = {
    Channel.CHAT: ChannelConfig(
        lookback_days=45,
        future_fill_lookback_days=45,
        extended_lookback_days=180,
        page_size=3,
        suppress_faststart=False,
        actions_execute_inline=False,
    ),
    Channel.VOICE: ChannelConfig(
        lookback_days=10,
        future_fill_lookback_days=30,
        extended_lookback_days=None,
        page_size=3,
        suppress_faststart=True,
        actions_execute_inline=True,
    ),
}


def for_channel(channel: Channel) -> ChannelConfig:
    """Return the behavior config for a channel.

    Args:
        channel: The active delivery channel.

    Returns:
        The immutable :class:`ChannelConfig` for that channel.
    """
    return _CONFIG[channel]
