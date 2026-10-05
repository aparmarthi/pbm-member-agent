"""Tests for the authentication tier logic."""

from __future__ import annotations

from src.config.auth import (
    AuthLevel,
    AuthState,
    CallerType,
    register_dob_attempt,
    requires_step_up,
    route_caller_type,
    valid_member_id,
    valid_rx_number,
)


def test_phi_intent_requires_step_up():
    assert requires_step_up("order_status", AuthLevel.NONE) is True
    assert requires_step_up("order_status", AuthLevel.LEVEL_1_5) is False
    assert requires_step_up("closing", AuthLevel.NONE) is False


def test_member_id_validation():
    assert valid_member_id("123456789") is True       # 9 digits
    assert valid_member_id("S1770707201") is True      # alphanumeric
    assert valid_member_id("12345") is False           # too short


def test_rx_number_validation():
    assert valid_rx_number("403314569") is True
    assert valid_rx_number("RX-403310002") is True
    assert valid_rx_number("123") is False             # too short
    assert valid_rx_number("ABCDEFGH") is False        # non-numeric


def test_dob_recovery_state_machine():
    st = AuthState()
    assert register_dob_attempt(st, success=False) == "reprompt"
    assert register_dob_attempt(st, success=False) == "defer"
    assert register_dob_attempt(st, success=True) == "verified"


def test_caller_type_routing():
    assert route_caller_type(CallerType.MEMBER) == "member_flow"
    assert route_caller_type(CallerType.PHARMACIST) == "pharmacy_help_desk"
    assert route_caller_type(CallerType.DOCTOR) == "icm_clinical"
