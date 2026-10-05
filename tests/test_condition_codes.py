"""Tests for the refill condition-code truth table."""

from __future__ import annotations

from src.config.condition_codes import (
    RefillOutcome,
    classify,
    is_refillable,
    list_priority,
)


def test_code_0_ready_and_cartable():
    cc = classify("0")
    assert cc.outcome is RefillOutcome.READY
    assert cc.can_add_to_cart is True
    assert is_refillable("0") is True


def test_remap_2_to_17_renewal():
    cc = classify("2")
    assert cc.code == 17
    assert cc.outcome is RefillOutcome.RENEWAL_REQUIRED


def test_controlled_substance_not_refillable():
    for code in ("5", "9", "15"):
        cc = classify(code)
        assert cc.outcome is RefillOutcome.CONTROLLED
        assert cc.can_add_to_cart is False


def test_unconfigured_code_transfers():
    for code in ("8", "12", "16"):
        cc = classify(code)
        assert cc.outcome is RefillOutcome.TRANSFER
        assert cc.transfer is True


def test_missing_code_transfers():
    assert classify(None).transfer is True
    assert classify("abc").transfer is True


def test_code_18_excluded_from_listing():
    # 18 is refillable but must not appear in the listable set.
    assert is_refillable("18") is True
    assert list_priority("18") is None


def test_list_priority_ready_before_renewal():
    assert list_priority("0") < list_priority("17")
