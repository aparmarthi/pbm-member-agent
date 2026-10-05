"""End-to-end tests for refill and drug-price nodes via the graph."""

from __future__ import annotations

import pytest

from src.data import synthetic
from src.graph.build import build_graph
from src.graph.tools import price_drug
from src.models.schemas import Channel


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def _run(graph, text, scenario, channel=Channel.CHAT):
    member = synthetic.build(scenario)
    return graph.invoke({
        "user_input": text, "channel": channel, "member": member,
        "is_verified": True, "messages": [("user", text)],
    })


def _reply(result) -> str:
    return result["messages"][-1].content


def test_refill_lists_ready_prescriptions(graph):
    result = _run(graph, "I want to refill my prescriptions", "refill_mixed_conditions")
    cands = result["refill_candidates"]
    listable = [c for c in cands if c.list_priority is not None]
    assert listable, "expected at least one refillable prescription"
    # Ready (code 0) sorts first.
    assert listable[0].outcome == "ready"


def test_refill_transfer_code_escalates(graph):
    result = _run(graph, "refill my meds", "refill_transfer_only")
    assert result["escalated"] is True
    assert result["handoff_target"] == "live_agent"


def test_refill_no_prescriptions(graph):
    result = _run(graph, "refill please", "no_orders")
    assert result["refill_candidates"] == []
    assert "don't see any prescriptions" in _reply(result)


def test_drug_price_covered():
    quote = price_drug("atorvastatin")
    assert quote.covered is True and quote.price is not None


def test_drug_price_prior_auth():
    quote = price_drug("Wegovy")
    assert quote.prior_auth_required is True


def test_drug_price_not_covered_offers_alternative():
    quote = price_drug("Abilify")
    assert quote.covered is False


def test_drug_price_node_needs_drug(graph):
    result = _run(graph, "how much does my medication cost?", "single_patient_mixed_statuses")
    # No recognizable drug name -> disambiguation prompt.
    assert "which medication" in _reply(result).lower()


def test_drug_price_node_resolves_named_drug(graph):
    result = _run(graph, "how much is wegovy?", "single_patient_mixed_statuses")
    assert result["price_quote"] is not None
    assert "prior authorization" in _reply(result).lower()
