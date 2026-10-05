"""Graph assembly — the open-stack equivalent of the agent bundle.

Wiring:

    crisis_gate → route → auth_gate → (proceed?) → intent node → END
                                    → (pending_auth) → END

The crisis gate runs before the LLM router so self-harm intent is pinned to
escalation deterministically. The auth gate runs after routing and enforces
Level 1.5 step-up before any PHI-exposing intent. Topics map to nodes;
``@utils.transition`` maps to conditional edges.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import auth_gate as auth_node
from src.graph.nodes import drug_price as price_node
from src.graph.nodes import order_status as os_node
from src.graph.nodes import refill as refill_node
from src.graph.nodes import router as router_node
from src.graph.nodes import stubs
from src.graph.state import AgentState
from src.utils.llm import LLMProvider, get_provider

# Intent → node name (the destinations the auth gate can proceed to).
_INTENT_NODES = {
    "order_status": "order_status",
    "order_action": "order_action",
    "refill": "refill",
    "drug_price": "drug_price",
    "escalation": "escalation",
    "closing": "closing",
    "off_topic": "off_topic",
}


def build_graph(provider: LLMProvider | None = None):
    """Construct and compile the agent graph.

    Args:
        provider: LLM backend; defaults to the env-selected provider.

    Returns:
        A compiled LangGraph runnable.
    """
    provider = provider or get_provider()
    g = StateGraph(AgentState)

    g.add_node("crisis_gate", router_node.crisis_gate)
    g.add_node("route", partial(router_node.route, provider=provider))
    g.add_node("auth_gate", auth_node.auth_gate)
    g.add_node("order_status", os_node.order_status)
    g.add_node("order_action", stubs.order_action)
    g.add_node("refill", refill_node.refill)
    g.add_node("drug_price", price_node.drug_price)
    g.add_node("escalation", stubs.escalation)
    g.add_node("closing", stubs.closing)
    g.add_node("off_topic", stubs.off_topic)

    g.add_edge(START, "crisis_gate")
    g.add_edge("crisis_gate", "route")
    g.add_edge("route", "auth_gate")

    # After the auth gate: pause for a token (pending_auth) or proceed to the
    # routed intent node. When pausing, we end the turn after the prompt.
    def gate_selector(state: AgentState) -> str:
        if auth_node.auth_selector(state) == "pending_auth":
            return "__end__"
        return router_node.route_selector(state)

    g.add_conditional_edges("auth_gate", gate_selector, {**_INTENT_NODES, "__end__": END})
    for terminal in _INTENT_NODES.values():
        g.add_edge(terminal, END)

    return g.compile()
