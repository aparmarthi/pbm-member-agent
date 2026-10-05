"""Tests for the deterministic reason-code catalog and priority ranking."""

from __future__ import annotations

from src.config.reason_codes import (
    PRIORITY_DELIVERED,
    PRIORITY_SELF_SERVE,
    lookup,
    priority_rank,
)


def test_lookup_known_code():
    rc = lookup("PAYMENT_METHOD_HOLD_RC54")
    assert rc is not None
    assert rc.status == "We need your help"
    assert "CHANGE_PAYMENT_METHOD" in [o.value for o in rc.self_serve]


def test_lookup_unknown_returns_none():
    assert lookup("NOT_A_REAL_CODE") is None
    assert lookup(None) is None


def test_rc14_escalates():
    rc = lookup("ONHOLD_RC14")
    assert rc is not None and rc.escalate is True


def test_rc13_routes_to_refill():
    rc = lookup("PAYMENT_METHOD_HOLD_RC13")
    assert rc is not None and rc.go_to_refill is True


def test_faststart_suppressed():
    rc = lookup("FASTSTART_2_REQUEST_SENT")
    assert rc is not None and rc.suppress is True


def test_priority_self_serve_beats_delivered():
    hold = lookup("PAYMENT_METHOD_HOLD_RC54")
    delivered = lookup("DELIVERED_OHS_RC49")
    assert priority_rank(hold) == PRIORITY_SELF_SERVE
    assert priority_rank(delivered) == PRIORITY_DELIVERED
    assert priority_rank(hold) < priority_rank(delivered)
