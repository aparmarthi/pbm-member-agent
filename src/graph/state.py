"""LangGraph state schema.

This ``TypedDict`` is the open-stack equivalent of Agentforce's ``variables:``
block. Where Agentforce marks variables Internal/External and
``filter_from_agent``, here we simply control which fields ever enter an LLM
prompt (see nodes) — that is manual context engineering, and it is deliberate.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from src.config.auth import AuthState
from src.models.schemas import (
    Channel,
    Intent,
    Member,
    PriceQuote,
    RefillCandidate,
    ResolvedStatus,
)


class AgentState(TypedDict, total=False):
    """Rolling state threaded through every node in the graph.

    Attributes:
        messages: Conversation history (LangGraph-managed, append-only).
        channel: chat | voice — drives lookback, pagination, action behavior.
        member: The authenticated member and accessible patients (grounding truth).
        is_verified: Whether identity verification (auth gate) has passed.
        intent: Router's resolved intent for the current turn.
        user_input: The current raw member utterance.
        resolved: Deterministically resolved + ranked statuses for this turn.
        page: 1-based pagination cursor.
        has_more: Whether more statuses remain beyond the current page.
        escalated: Set once the turn hands off to a human.
        handoff_target: Handoff destination marker, if escalated.
        auth: Session authentication progress.
        drug_query: Drug name/params for a pricing turn.
        refill_candidates: Refill-evaluated prescriptions for this turn.
        price_quote: Resolved pricing/coverage for this turn.
    """

    messages: Annotated[list, add_messages]
    channel: Channel
    member: Member | None
    is_verified: bool
    intent: Intent | None
    user_input: str
    resolved: list[ResolvedStatus]
    page: int
    has_more: bool
    escalated: bool
    handoff_target: str | None
    auth: AuthState
    drug_query: str | None
    refill_candidates: list[RefillCandidate]
    price_quote: PriceQuote | None
