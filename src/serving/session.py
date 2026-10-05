"""Multi-turn session wrapper shared by the CLI, API, Streamlit demo, and evals.

One compiled graph with an in-memory checkpointer serves every session; each
session is a ``thread_id``. State (pending offers, pagination, auth progress)
survives between turns, which is what makes "yes, show me the rest" and
token → DOB authentication work.

``MemorySaver`` keeps every thread in process memory — fine for a demo. A
deployment would swap in a persistent saver (e.g. Postgres) with a TTL.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.config.channels import for_channel
from src.data import synthetic
from src.graph.build import build_graph
from src.models.schemas import AgentTurnResult, Channel, Intent
from src.utils.llm import LLMProvider


# Domain types the checkpointer may rebuild from saved state. LangGraph is moving
# to block unregistered types on deserialization, so the allowlist is explicit.
_CHECKPOINT_TYPES = [
    ("src.models.schemas", name)
    for name in ("Channel", "Intent", "Member", "ResolvedStatus", "RefillCandidate", "PriceQuote")
] + [("src.config.auth", name) for name in ("AuthState", "AuthLevel", "CallerType")]


def _saver() -> MemorySaver:
    return MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES))


@lru_cache(maxsize=1)
def default_graph():
    """Return the process-wide checkpointed graph (env-selected LLM provider)."""
    return build_graph(checkpointer=_saver())


class AgentSession:
    """One member conversation on one channel.

    Args:
        scenario: Synthetic member scenario name (see ``synthetic.SCENARIOS``).
        channel: Delivery channel.
        verified: Whether the session starts authenticated (chat behind a web
            login). ``False`` exercises step-up auth (token → DOB).
        provider: Optional LLM override; builds a dedicated graph when given.
    """

    def __init__(
        self,
        scenario: str,
        channel: Channel = Channel.CHAT,
        verified: bool = True,
        provider: LLMProvider | None = None,
    ) -> None:
        self.scenario = scenario
        self.member = synthetic.build(scenario)
        self.channel = channel
        self.verified = verified
        self.thread_id = uuid4().hex
        self._graph = (build_graph(provider, checkpointer=_saver())
                       if provider else default_graph())

    def send(self, text: str) -> AgentTurnResult:
        """Run one member utterance through the graph.

        Args:
            text: The member's message.

        Returns:
            The agent's reply plus the decisions the graph made this turn.
        """
        result = self._graph.invoke(
            {
                "user_input": text,
                "channel": self.channel,
                "member": self.member,
                "is_verified": self.verified,
                "messages": [("user", text)],
            },
            {"configurable": {"thread_id": self.thread_id}},
        )
        intent = result.get("intent") or Intent.OFF_TOPIC
        shown = []
        if intent is Intent.ORDER_STATUS and result.get("resolved"):
            size = for_channel(self.channel).page_size
            start = (result.get("page", 1) - 1) * size
            shown = result["resolved"][start:start + size]
        return AgentTurnResult(
            reply=result["messages"][-1].content,
            intent=intent,
            escalated=bool(result.get("escalated")),
            handoff_target=result.get("handoff_target"),
            shown=shown,
            has_more=bool(result.get("has_more")) and intent is Intent.ORDER_STATUS,
        )
