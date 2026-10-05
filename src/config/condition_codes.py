"""Refill condition-code catalog: the deterministic truth table for refill eligibility.

The refill equivalent of ``reason_codes``. Each condition code maps to an
eligibility outcome, member-facing copy, and whether the prescription may be
added to the cart or must transfer to a human. Encodes the exact remapping and
priority rules from the refill user stories (TLPDMSF-120 and the per-condition
stories 343/344/347/354–361/122).

These are drug-eligibility codes and copy — not member data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RefillOutcome(str, Enum):
    """What the agent can do with a prescription given its condition code."""

    READY = "ready"                    # 0: refillable now
    RENEWAL_REQUIRED = "renewal"       # 17,18,19,20: needs prescriber renewal
    PARTICIPANT_HOLD = "participant"   # 21: hold released by ordering
    SHIP_CONSENT = "ship_consent"      # 26,27: needs consent to ship
    TOO_EARLY = "too_early"            # 1,13: too soon to refill
    TOO_OLD = "too_old"                # 2,6: Rx too old (2->17, 6->18 remap)
    NOT_REFILLABLE = "not_refillable"  # 7,10,11: out of refills (10->19,11->20)
    CONTROLLED = "controlled"          # 5,9,15: controlled substance
    NOT_AVAILABLE = "not_available"    # 4,22,23: drug no longer available
    PRESCRIBER_HOLD = "prescriber_hold"  # 24
    IN_PROGRESS = "in_progress"        # 3: order already in progress
    TRANSFER = "transfer"              # 8,12,14,16, unconfigured, errors


# Rule 11-14 remaps applied before classification.
_REMAP: dict[int, int] = {2: 17, 10: 19, 11: 20, 6: 18}

# Refillable set (post-remap) per TLPDMSF-120. 18 is excluded from *listing*.
_REFILLABLE = {0, 17, 18, 19, 20, 26, 27, 21}
# Listing priority (lower first). 0-today handled separately from 0-future.
_LIST_PRIORITY = {0: 0, 17: 2, 19: 3, 20: 4, 26: 5, 27: 6, 21: 7}
_LIST_EXCLUDED = {18}  # expired controlled substance — refillable but not listed


@dataclass(frozen=True)
class ConditionCode:
    """One row of the refill eligibility truth table.

    Attributes:
        code: Canonical (post-remap) numeric condition code.
        outcome: The eligibility outcome bucket.
        message: Member-facing explanation copy.
        can_add_to_cart: Whether the Rx may be added to the refill cart.
        transfer: Whether this code forces a human transfer.
        refillable: Whether the code counts as refillable for listing.
    """

    code: int
    outcome: RefillOutcome
    message: str
    can_add_to_cart: bool = False
    transfer: bool = False
    refillable: bool = False


_ROWS: tuple[ConditionCode, ...] = (
    ConditionCode(0, RefillOutcome.READY,
                  "This prescription is ready to refill now.", can_add_to_cart=True, refillable=True),
    ConditionCode(1, RefillOutcome.TOO_EARLY,
                  "It's too early to refill this prescription right now."),
    ConditionCode(13, RefillOutcome.TOO_EARLY,
                  "It's too early to refill this prescription right now."),
    ConditionCode(3, RefillOutcome.IN_PROGRESS,
                  "An order is already in progress for this prescription."),
    ConditionCode(17, RefillOutcome.RENEWAL_REQUIRED,
                  "This prescription needs a renewal from your prescriber before it can be dispensed.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(18, RefillOutcome.RENEWAL_REQUIRED,
                  "This prescription needs a renewal from your prescriber before it can be dispensed.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(19, RefillOutcome.RENEWAL_REQUIRED,
                  "This prescription needs a renewal from your prescriber before it can be dispensed.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(20, RefillOutcome.RENEWAL_REQUIRED,
                  "This prescription needs a renewal from your prescriber before it can be dispensed.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(21, RefillOutcome.PARTICIPANT_HOLD,
                  "This prescription has a hold that's removed when you place the order.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(26, RefillOutcome.SHIP_CONSENT,
                  "This prescription needs your consent to ship before it can be filled.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(27, RefillOutcome.SHIP_CONSENT,
                  "This prescription needs your consent to ship before it can be filled.",
                  can_add_to_cart=True, refillable=True),
    ConditionCode(7, RefillOutcome.NOT_REFILLABLE,
                  "You're out of refills for this prescription. Please contact your provider for next steps."),
    ConditionCode(2, RefillOutcome.TOO_OLD,
                  "This prescription is too old to be refilled. Please contact your provider."),
    ConditionCode(5, RefillOutcome.CONTROLLED,
                  "This prescription is for a controlled substance and can't be refilled here. "
                  "Please contact your provider."),
    ConditionCode(9, RefillOutcome.CONTROLLED,
                  "This prescription is for a controlled substance and can't be refilled here. "
                  "Please contact your provider."),
    ConditionCode(15, RefillOutcome.CONTROLLED,
                  "This prescription is for a controlled substance and can't be refilled here. "
                  "Please contact your provider."),
    ConditionCode(4, RefillOutcome.NOT_AVAILABLE,
                  "This medication is no longer available at mail order. Please contact your provider."),
    ConditionCode(22, RefillOutcome.NOT_AVAILABLE,
                  "This medication is no longer available at mail order. Please contact your provider."),
    ConditionCode(23, RefillOutcome.NOT_AVAILABLE,
                  "This medication is no longer available at mail order. Please contact your provider."),
    ConditionCode(24, RefillOutcome.PRESCRIBER_HOLD,
                  "This prescription is on a prescriber hold."),
)

_BY_CODE: dict[int, ConditionCode] = {r.code: r for r in _ROWS}


def _parse(code: str | int | None) -> int | None:
    """Normalize a raw condition code to an int, or None if unparseable."""
    if code is None:
        return None
    try:
        return int(str(code).strip())
    except ValueError:
        return None


def classify(raw_code: str | int | None) -> ConditionCode:
    """Classify a raw refill condition code into its eligibility row.

    Applies the remap rules (2→17, 6→18, 10→19, 11→20), then looks up the row.
    Unknown/unconfigured codes (8, 12, 14, 16, errors, missing) resolve to a
    TRANSFER outcome per TLPDMSF-361.

    Args:
        raw_code: The condition code as returned by the eligibility service.

    Returns:
        The matching :class:`ConditionCode`; a synthetic TRANSFER row for
        anything unconfigured.
    """
    code = _parse(raw_code)
    if code is None:
        return ConditionCode(-1, RefillOutcome.TRANSFER,
                             "I'll connect you with someone who can help with this prescription.",
                             transfer=True)
    code = _REMAP.get(code, code)
    row = _BY_CODE.get(code)
    if row is None:
        return ConditionCode(code, RefillOutcome.TRANSFER,
                             "I'll connect you with someone who can help with this prescription.",
                             transfer=True)
    return row


def is_refillable(raw_code: str | int | None) -> bool:
    """Return True if the (remapped) code counts as refillable.

    Args:
        raw_code: Raw condition code.

    Returns:
        Whether the prescription is refillable.
    """
    code = _parse(raw_code)
    if code is None:
        return False
    return _REMAP.get(code, code) in _REFILLABLE


def list_priority(raw_code: str | int | None, *, future_fill: bool = False) -> int | None:
    """Compute the refill-list sort priority for a code.

    Args:
        raw_code: Raw condition code.
        future_fill: For code 0, whether the fill date is in the future
            (future-dated code 0 sorts after today-dated code 0).

    Returns:
        Integer priority (lower first), or None if the code is excluded from
        listing (e.g. 18) or not refillable.
    """
    code = _parse(raw_code)
    if code is None:
        return None
    code = _REMAP.get(code, code)
    if code in _LIST_EXCLUDED or code not in _REFILLABLE:
        return None
    base = _LIST_PRIORITY.get(code, 8)
    if code == 0 and future_fill:
        base = 1
    return base
