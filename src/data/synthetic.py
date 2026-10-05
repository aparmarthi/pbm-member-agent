"""Synthetic member/order data generator.

Reproduces the *structure* of the PBM order payload (member → patients → orders
→ prescriptions) with entirely fabricated values. No real member data is used or
required. Scenario builders mirror the named test scenarios from the source
requirements (multi-patient family, payment holds, mixed statuses, no-orders,
refill-eligible, escalation-required) so evals exercise real edge cases.

Determinism: a seeded ``random.Random`` is threaded through so fixtures are
reproducible without relying on global RNG state.
"""

from __future__ import annotations

import random

from src.config.reason_codes import CATALOG
from src.models.schemas import Member, Order, Patient, Prescription

_FIRST_NAMES = ["Ada", "Rumi", "Kai", "Nova", "Favi", "Iris", "Otto", "Zia", "Milo", "Esme"]
_LAST_NAMES = ["Vega", "Rowe", "Tan", "Okoro", "Reyes", "Haas", "Lindqvist", "Baptiste"]
_DRUGS = [
    "ATORVASTATIN 20MG TAB", "LISINOPRIL 10MG TAB", "PEPCID 20MG TAB",
    "JANUVIA 50MG TAB", "SYNTHROID 50MCG TAB", "BRILINTA 60MG TAB",
    "ACTOS 30MG TAB", "AMOXICILLIN 500MG TAB", "TOPAMAX 50MG TAB",
]
# A representative slice of the catalog covering each priority tier.
_STATUS_POOL = [
    "PAYMENT_METHOD_HOLD_RC54", "HIGH_COPAY_HOLD_RC51", "SHIP_CONSENT_HOLD_RC11",
    "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48", "PROCESSING_CHECK_INVENTORY_RC4",
    "SHIPPED_OHS_RC8_42_NO_TRACKING", "DELIVERED_OHS_RC49", "FUTURE_FILL_RC60",
    "PA_REQUIRED_RC68", "CANCELED_RC23",
]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _fake_id(rng: random.Random, width: int = 9) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(width))


def _make_rx(
    rng: random.Random,
    status_code: str,
    drug: str | None = None,
    condition_code: str | None = None,
) -> Prescription:
    cond = condition_code if condition_code is not None else rng.choice(["0", "17", "21", "3"])
    return Prescription(
        rx_number=_fake_id(rng, 9),
        drug_name=drug or rng.choice(_DRUGS),
        status_code=status_code,
        condition_code=cond,
        price=round(rng.uniform(5, 320), 2),
    )


def _make_order(rng: random.Random, status_code: str, n_rx: int = 1) -> Order:
    return Order(
        order_number=_fake_id(rng, 10),
        order_date="2026-06-15",
        prescriptions=[_make_rx(rng, status_code) for _ in range(n_rx)],
        tracking_id=_fake_id(rng, 12) if status_code.startswith("SHIPPED") else None,
    )


def _patient(rng: random.Random, rel: str, *, status_codes: list[str]) -> Patient:
    return Patient(
        internal_id=_fake_id(rng),
        first_name=rng.choice(_FIRST_NAMES),
        last_name=rng.choice(_LAST_NAMES),
        dob="1988-01-01",
        relationship=rel,  # type: ignore[arg-type]
        orders=[_make_order(rng, sc) for sc in status_codes],
    )


# ---- Named scenarios (mirror source test-data scenario labels) ----


def single_patient_mixed_statuses(seed: int = 1) -> Member:
    """One member, multiple orders spanning several priority tiers."""
    rng = _rng(seed)
    codes = ["PAYMENT_METHOD_HOLD_RC54", "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48",
             "SHIPPED_OHS_RC8_42_NO_TRACKING", "DELIVERED_OHS_RC49", "FUTURE_FILL_RC60"]
    self_patient = _patient(rng, "self", status_codes=codes)
    return Member(member_id=_fake_id(rng, 11), internal_id=self_patient.internal_id,
                  patients=[self_patient])


def family_plan(seed: int = 2) -> Member:
    """Account holder plus spouse and child, each with active orders."""
    rng = _rng(seed)
    holder = _patient(rng, "self", status_codes=["SHIPPED_OHS_RC8_42_NO_TRACKING"])
    spouse = _patient(rng, "spouse", status_codes=["HIGH_COPAY_HOLD_RC51"])
    child = _patient(rng, "child", status_codes=["PROCESSING_CHECK_INVENTORY_RC4"])
    return Member(member_id=_fake_id(rng, 11), internal_id=holder.internal_id,
                  patients=[holder, spouse, child])


def no_orders(seed: int = 3) -> Member:
    """Member with zero orders in any window (escalation / refill-check path)."""
    rng = _rng(seed)
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1990-01-01", relationship="self")
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def escalation_required(seed: int = 4) -> Member:
    """Member whose only order carries a must-transfer Caremark hold (RC14)."""
    rng = _rng(seed)
    p = _patient(rng, "self", status_codes=["ONHOLD_RC14"])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def payment_hold(seed: int = 5) -> Member:
    """Member with a resolvable payment-method hold (action-path fixture)."""
    rng = _rng(seed)
    p = _patient(rng, "self", status_codes=["PAYMENT_METHOD_HOLD_RC54"])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def refill_mixed_conditions(seed: int = 6) -> Member:
    """Member with prescriptions spanning refill condition codes.

    Covers ready-to-refill (0), renewal (17), controlled substance (5, cannot
    refill), too-early (1), and an unconfigured transfer code (8).
    """
    rng = _rng(seed)
    orders = [
        Order(order_number=_fake_id(rng, 10), order_date="2026-06-01",
              prescriptions=[_make_rx(rng, "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48",
                                      drug="ATORVASTATIN 20MG TAB", condition_code="0")]),
        Order(order_number=_fake_id(rng, 10), order_date="2026-06-01",
              prescriptions=[_make_rx(rng, "RENEWAL_NO_FILLS_RC83",
                                      drug="LISINOPRIL 10MG TAB", condition_code="17")]),
        Order(order_number=_fake_id(rng, 10), order_date="2026-06-01",
              prescriptions=[_make_rx(rng, "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48",
                                      drug="ADDERALL 20MG TAB", condition_code="5")]),
        Order(order_number=_fake_id(rng, 10), order_date="2026-06-01",
              prescriptions=[_make_rx(rng, "FUTURE_FILL_RC60",
                                      drug="PEPCID 20MG TAB", condition_code="1")]),
    ]
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=orders)
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def refill_transfer_only(seed: int = 7) -> Member:
    """Member whose only Rx has an unconfigured condition code (forces transfer)."""
    rng = _rng(seed)
    o = Order(order_number=_fake_id(rng, 10), order_date="2026-06-01",
              prescriptions=[_make_rx(rng, "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48",
                                      drug="TOPAMAX 50MG TAB", condition_code="8")])
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=[o])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


SCENARIOS = {
    "single_patient_mixed_statuses": single_patient_mixed_statuses,
    "family_plan": family_plan,
    "no_orders": no_orders,
    "escalation_required": escalation_required,
    "payment_hold": payment_hold,
    "refill_mixed_conditions": refill_mixed_conditions,
    "refill_transfer_only": refill_transfer_only,
}


def build(scenario: str, seed: int | None = None) -> Member:
    """Build a synthetic member for a named scenario.

    Args:
        scenario: One of :data:`SCENARIOS`.
        seed: Optional seed override for reproducibility.

    Returns:
        A fully populated synthetic :class:`Member`.

    Raises:
        KeyError: If the scenario name is unknown.
    """
    fn = SCENARIOS[scenario]
    return fn() if seed is None else fn(seed)
