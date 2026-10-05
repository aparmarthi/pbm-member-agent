"""End-to-end graph tests using the mock provider (hermetic, zero-cost)."""

from __future__ import annotations

import pytest

from src.data import synthetic
from src.graph.build import build_graph
from src.models.schemas import Channel


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def _run(graph, text, scenario="single_patient_mixed_statuses", channel=Channel.CHAT):
    member = synthetic.build(scenario)
    return graph.invoke({
        "user_input": text, "channel": channel, "member": member,
        "is_verified": True, "messages": [("user", text)],
    })


def _reply(result) -> str:
    return result["messages"][-1].content


def test_crisis_input_routes_to_escalation_with_988(graph):
    result = _run(graph, "I want to kill myself")
    assert result["escalated"] is True
    assert "988" in _reply(result)


def test_human_request_escalates(graph):
    result = _run(graph, "let me talk to a representative")
    assert result["escalated"] is True


def test_order_status_returns_orders(graph):
    result = _run(graph, "where is my order?")
    assert result["resolved"], "expected resolved statuses"
    assert "last 45 days" in _reply(result)


def test_rc14_order_forces_escalation(graph):
    result = _run(graph, "where is my order?", scenario="escalation_required")
    assert result["escalated"] is True
    assert result["handoff_target"] == "live_agent"


def test_no_orders_offers_help(graph):
    result = _run(graph, "where is my order?", scenario="no_orders")
    assert result["resolved"] == []
    assert "didn't find" in _reply(result)


def test_voice_pagination_phrasing(graph):
    result = _run(graph, "where are my orders?", channel=Channel.VOICE)
    if result["has_more"]:
        assert "hear the other" in _reply(result)


def test_priority_hold_surfaces_first(graph):
    result = _run(graph, "where are my orders?")
    resolved = result["resolved"]
    assert resolved[0].priority <= resolved[-1].priority
