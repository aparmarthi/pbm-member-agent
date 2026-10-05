"""Deterministic tools — the "code decides truth" half of the design.

These are plain typed functions (the open-stack equivalent of Agentforce
``apex://`` actions). The LLM never fabricates their output; it only chooses
which to call and narrates the result.
"""

from __future__ import annotations

from datetime import date

from src.config.channels import for_channel
from src.config.condition_codes import classify, is_refillable, list_priority
from src.config.reason_codes import lookup, priority_rank
from src.models.schemas import (
    Channel,
    Member,
    PriceQuote,
    RefillCandidate,
    ResolvedStatus,
)


def fetch_orders(member: Member) -> Member:
    """Return the member's orders (identity injected at request time).

    In production this is an authenticated API callout. Here it is a pass-through
    over the synthetic member already loaded into session context, which keeps
    the grounding contract explicit: the agent only ever sees this member's data.

    Args:
        member: The authenticated member with accessible patients/orders.

    Returns:
        The same member (the seam where a real API integration would live).
    """
    return member


def _in_window(order_date: str | None, days: int, as_of: date) -> bool:
    """Return True if an order falls inside a lookback window (undated orders count)."""
    if not order_date:
        return True
    return (as_of - date.fromisoformat(order_date)).days <= days


def resolve_statuses(
    member: Member,
    channel: Channel,
    *,
    lookback_days: int | None = None,
    as_of: date | None = None,
) -> list[ResolvedStatus]:
    """Flatten orders into resolved, ranked, channel-filtered statuses.

    Applies the lookback window (future fills get the channel's longer window),
    the deterministic reason-code catalog, suppresses hidden statuses (and
    FastStart on voice), attaches self-serve options / CTAs, and sorts by shared
    priority ranking then drug name for stable output.

    Args:
        member: Member whose orders to resolve.
        channel: Active channel (controls window and FastStart suppression).
        lookback_days: Window override (e.g. chat's 6-month extended search);
            defaults to the channel's primary window.
        as_of: Reference date for the window; defaults to today.

    Returns:
        Priority-sorted list of :class:`ResolvedStatus`, suppressed and
        out-of-window items removed.
    """
    cfg = for_channel(channel)
    days = lookback_days or cfg.lookback_days
    as_of = as_of or date.today()
    out: list[ResolvedStatus] = []
    for patient in member.patients:
        name = f"{patient.first_name} {patient.last_name}"
        for order in patient.orders:
            for rx in order.prescriptions:
                window = days
                if rx.status_code.startswith("FUTURE_FILL"):
                    window = max(days, cfg.future_fill_lookback_days)
                if not _in_window(order.order_date, window, as_of):
                    continue
                rc = lookup(rx.status_code)
                if rc and rc.suppress:
                    continue
                if cfg.suppress_faststart and rx.status_code.startswith("FASTSTART"):
                    continue
                out.append(
                    ResolvedStatus(
                        patient_name=name,
                        drug_name=rx.drug_name,
                        status=rc.status if rc else "Pending",
                        sub_status=rc.sub_status if rc else "We'll have an update soon.",
                        parent_status=rc.parent_status.value if rc else "We're working on it",
                        order_number=order.order_number,
                        priority=priority_rank(rc),
                        self_serve=[o.value for o in rc.self_serve] if rc else [],
                        primary_cta=rc.primary_cta if rc else None,
                        escalate=rc.escalate if rc else False,
                        go_to_refill=rc.go_to_refill if rc else False,
                        tracking_id=order.tracking_id,
                        price=rx.price,
                    )
                )
    out.sort(key=lambda s: (s.priority, s.drug_name))
    return out


def check_refill_eligibility(member: Member) -> list[RefillCandidate]:
    """Evaluate every prescription for refill eligibility, sorted for listing.

    Mirrors the Check Refill Eligibility service contract: each Rx's condition
    code is classified deterministically, refillable Rxs are sorted by list
    priority, and non-refillable ones are retained (the agent still informs the
    member and moves on per the per-condition stories). An Rx whose current
    order carries a must-transfer hold (e.g. RC14) is never offered for refill —
    it transfers, matching what Order Status says about the same Rx.

    Args:
        member: Member whose prescriptions to evaluate.

    Returns:
        Refill candidates; refillable-and-listable ones first (by priority),
        then the rest.
    """
    candidates: list[RefillCandidate] = []
    for patient in member.patients:
        name = f"{patient.first_name} {patient.last_name}"
        for order in patient.orders:
            for rx in order.prescriptions:
                cc = classify(rx.condition_code)
                rc = lookup(rx.status_code)
                if rc and rc.escalate:
                    candidates.append(RefillCandidate(
                        patient_name=name, drug_name=rx.drug_name, rx_number=rx.rx_number,
                        condition_code=rx.condition_code, outcome="transfer",
                        message="This prescription has a hold a specialist needs to resolve.",
                        transfer=True, price=rx.price,
                    ))
                    continue
                candidates.append(
                    RefillCandidate(
                        patient_name=name,
                        drug_name=rx.drug_name,
                        rx_number=rx.rx_number,
                        condition_code=rx.condition_code,
                        outcome=cc.outcome.value,
                        message=cc.message,
                        can_add_to_cart=cc.can_add_to_cart,
                        transfer=cc.transfer,
                        list_priority=list_priority(rx.condition_code),
                        price=rx.price,
                    )
                )

    def sort_key(c: RefillCandidate) -> tuple[int, int, str]:
        listable = c.list_priority is not None
        return (0 if listable else 1, c.list_priority if listable else 99, c.drug_name)

    candidates.sort(key=sort_key)
    return candidates


# --- Drug pricing (mock benefit lookup; deterministic + explainable) ---

# Drugs requiring prior authorization; drugs not covered under the mock plan.
_PA_REQUIRED = {"WEGOVY", "ZEPBOUND", "SAXENDA", "VYVANSE", "ADDERALL"}
_NOT_COVERED = {"ABILIFY"}
# Brand → generic alternatives surfaced when a brand is expensive/not covered.
_ALTERNATIVES = {
    "LIPITOR": ["ATORVASTATIN"],
    "SYNTHROID": ["LEVOTHYROXINE"],
    "NEXIUM": ["ESOMEPRAZOLE"],
}


def price_drug(drug_name: str, *, strength: str | None = None) -> PriceQuote:
    """Return a coverage/price quote for a drug (mock benefit lookup).

    Deterministic stand-in for the drugPrice experience API. Handles the three
    outcomes the pricing stories require: not-covered, prior-auth-required, and
    a covered price (with generic alternatives when available).

    Args:
        drug_name: Requested drug name (brand or generic), case-insensitive.
        strength: Optional strength; unused in the mock but part of the contract.

    Returns:
        A :class:`PriceQuote`.
    """
    key = drug_name.strip().upper().split()[0] if drug_name.strip() else ""
    if not key:
        return PriceQuote(drug_name=drug_name, covered=False,
                          message="I didn't catch the medication name — which drug did you mean?")
    if key in _NOT_COVERED:
        return PriceQuote(
            drug_name=drug_name, covered=False,
            message=f"{drug_name} isn't covered under your plan.",
            alternatives=_ALTERNATIVES.get(key, []),
        )
    # Deterministic pseudo-price from the name so tests are stable.
    price = round(10 + sum(ord(c) for c in key) % 90 + 0.99, 2)
    if key in _PA_REQUIRED:
        # Price is the cost once PA is approved — offered, not volunteered.
        return PriceQuote(
            drug_name=drug_name, covered=True, prior_auth_required=True, price=price,
            message=(f"{drug_name} requires a prior authorization before it's covered. "
                     "Contact your prescriber to start the request. "
                     "Would you like to hear the estimated cost?"),
        )
    return PriceQuote(
        drug_name=drug_name, covered=True, price=price,
        message=f"{drug_name} is covered. The estimated cost is ${price:.2f}.",
        alternatives=_ALTERNATIVES.get(key, []),
    )
