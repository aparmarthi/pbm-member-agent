"""Reason-code catalog: the deterministic truth table for order statuses.

This is the heart of the "LLM decides intent; code decides truth" design. Each
prescription's ``statusCode`` maps deterministically to a parent status, a
member-facing status label, sub-status copy, available self-serve options, and a
call-to-action. The LLM never invents any of this — it only selects intent and
narrates the resolved payload.

Sourced from the CX design reason-code / self-serve mappings. These are
drug-status codes and member-facing copy, NOT member data — safe to encode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ParentStatus(str, Enum):
    """Top-level lifecycle bucket used for priority ranking."""

    DELAYED = "Delayed"
    NOT_FILLED = "Not filled"
    WORKING_ON_IT = "We're working on it"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"


class SelfServeOption(str, Enum):
    """Actions a member may take to resolve a hold, per channel."""

    CHANGE_PAYMENT_METHOD = "CHANGE_PAYMENT_METHOD"
    HIGH_COST_HOLD_RELEASE = "HIGH_COST_HOLD_RELEASE"
    SHIP_CONSENT = "SHIP_CONSENT"
    SHIPMENT_HOLD = "SHIPMENT_HOLD"
    INDEFINITE_HOLD = "INDEFINITE_HOLD"
    CHANGE_FILL_DATE = "CHANGE_FILL_DATE"
    CHANGE_SHIPPING_ADDRESS = "CHANGE_SHIPPING_ADDRESS"
    CHANGE_SHIPPING_METHOD = "CHANGE_SHIPPING_METHOD"
    CANCEL_ELIGIBILITY = "CANCEL_ELIGIBILITY"
    GO_TO_REFILL = "GO_TO_REFILL"


@dataclass(frozen=True)
class ReasonCode:
    """One row of the deterministic status truth table.

    Attributes:
        code: Canonical status code as returned by the order API.
        parent_status: Lifecycle bucket, drives priority ranking.
        status: Member-facing status label.
        sub_status: Short member-facing explanation copy.
        self_serve: Self-serve options unlocked by this status.
        primary_cta: Call-to-action label shown/spoken to the member.
        escalate: True when this status must transfer to a human agent.
        suppress: True when this status should be hidden from the member
            (e.g. FastStart, certain mail-order reason codes).
        go_to_refill: True when the resolution path is the Refill flow.
    """

    code: str
    parent_status: ParentStatus
    status: str
    sub_status: str
    self_serve: tuple[SelfServeOption, ...] = field(default_factory=tuple)
    primary_cta: str | None = None
    escalate: bool = False
    suppress: bool = False
    go_to_refill: bool = False


# Priority order for presenting statuses (lower number = surfaced first).
# Shared across channels per the CX "Priority order for statuses" rule.
PRIORITY_SELF_SERVE = 1  # holds needing member action
PRIORITY_READY_PICKUP = 2
PRIORITY_EVERYTHING_ELSE = 3
PRIORITY_DELIVERED = 4


# The catalog. Multi-code aggregate keys (e.g. IN_PROCESS_RC2_3_5_6...) are kept
# verbatim because the upstream API emits them as single composite codes.
_CATALOG: tuple[ReasonCode, ...] = (
    # ---- Payment / cost holds (self-serve, highest priority) ----
    ReasonCode(
        "PAYMENT_METHOD_HOLD_RC54", ParentStatus.DELAYED, "We need your help",
        "There's a problem with your payment method. Please update it to continue this order.",
        (SelfServeOption.CHANGE_PAYMENT_METHOD,), "Update payment",
    ),
    ReasonCode(
        "HIGH_COPAY_HOLD_RC51", ParentStatus.DELAYED, "We need your help",
        "Your order has a high total cost. We need you to approve the order before we can ship it.",
        (SelfServeOption.HIGH_COST_HOLD_RELEASE, SelfServeOption.CHANGE_PAYMENT_METHOD),
        "Start approval",
    ),
    ReasonCode(
        "EXCEEDED_MAX_DOLLARS_HOLD_RC52", ParentStatus.DELAYED, "We need your help",
        "You've exceeded the maximum dollar benefit for your plan, so this order is on hold. "
        "You can approve it if you'd still like to get it.",
        (SelfServeOption.HIGH_COST_HOLD_RELEASE, SelfServeOption.CHANGE_PAYMENT_METHOD),
        "Start approval",
    ),
    ReasonCode(
        "BRAND_HIGHER_COPAY_HOLD_RC53", ParentStatus.DELAYED, "We need your help",
        "You can save money with a generic medication. Contact your prescriber for the generic, "
        "or approve this order to keep the higher cost.",
        (SelfServeOption.HIGH_COST_HOLD_RELEASE, SelfServeOption.CHANGE_PAYMENT_METHOD),
        "Start approval",
    ),
    # RC13: cancelled payment hold — routes to Refill rather than a hold release.
    ReasonCode(
        "PAYMENT_METHOD_HOLD_RC13", ParentStatus.NOT_FILLED, "Canceled",
        "This order was canceled because of a payment problem. You can reorder it now.",
        (SelfServeOption.GO_TO_REFILL,), "Start reorder", go_to_refill=True,
    ),
    # ---- Ship-consent holds ----
    ReasonCode(
        "SHIP_CONSENT_HOLD_RC11", ParentStatus.WORKING_ON_IT, "We need your help",
        "We need your approval before shipping this order.",
        (SelfServeOption.SHIP_CONSENT,), "Start approval",
    ),
    ReasonCode(
        "72HR_SHIP_CONSENT_HOLD_RC31", ParentStatus.NOT_FILLED, "Canceled",
        "This order was canceled because the shipment wasn't approved in time. You can reorder it now.",
        (SelfServeOption.SHIPMENT_HOLD,), "Start reorder", go_to_refill=True,
    ),
    # ---- Profile hold: always transfer to a human ----
    ReasonCode(
        "ONHOLD_RC14", ParentStatus.DELAYED, "We need your help",
        "There's a note on your profile that we need to resolve before this order can ship.",
        (), "Connect to Member Care Specialist", escalate=True,
    ),
    # ---- More-info hold: escalate (info needed the agent can't self-serve) ----
    ReasonCode(
        "MORE_INFO_RC7", ParentStatus.NOT_FILLED, "We need your help",
        "We need more information before we can fill this prescription.",
        (), "Connect to Member Care Specialist", escalate=True,
    ),
    # ---- In-process (no member action) ----
    ReasonCode(
        "IN_PROCESS_NO_DATE_RC2_3_5_6_36_37_43_44_45_46_47_48", ParentStatus.WORKING_ON_IT,
        "Preparing", "Your pharmacy team is preparing this prescription.",
        (SelfServeOption.CHANGE_FILL_DATE, SelfServeOption.CHANGE_SHIPPING_ADDRESS,
         SelfServeOption.CHANGE_SHIPPING_METHOD, SelfServeOption.CANCEL_ELIGIBILITY),
    ),
    ReasonCode(
        "IN_PROCESS_RC2_3_5_6_36_37_43_44_45_46_47_48", ParentStatus.WORKING_ON_IT,
        "Preparing", "Your pharmacy team is preparing this prescription.",
        (SelfServeOption.CHANGE_FILL_DATE, SelfServeOption.CHANGE_SHIPPING_ADDRESS,
         SelfServeOption.CHANGE_SHIPPING_METHOD, SelfServeOption.CANCEL_ELIGIBILITY),
    ),
    ReasonCode(
        "PROCESSING_CHECK_INVENTORY_RC4", ParentStatus.WORKING_ON_IT, "Preparing",
        "Your pharmacy team is preparing this prescription.",
    ),
    ReasonCode(
        "UNDER_REVIEW_RC104_106_107", ParentStatus.WORKING_ON_IT, "Preparing",
        "Your pharmacy team is reviewing this prescription.",
    ),
    ReasonCode(
        "AWATING_INVENTORY_RC105", ParentStatus.WORKING_ON_IT, "Pending",
        "We're waiting on inventory for this prescription.",
    ),
    ReasonCode(
        "PO_IN_PROCESS_RC1", ParentStatus.WORKING_ON_IT, "Pending",
        "Your order is being processed.",
    ),
    ReasonCode(
        "CMK_REQUEST_RESPONSE_DELAYED_TRANSIENT_STATUS", ParentStatus.WORKING_ON_IT, "Pending",
        "We'll update your order details once your pharmacy team reviews this request.",
    ),
    # ---- Shipped ----
    ReasonCode(
        "SHIPPED_OHS_RC8_42_NO_TRACKING", ParentStatus.SHIPPED, "On the way",
        "Your order is on the way.",
    ),
    ReasonCode(
        "SHIPPED_RC8_42_NO_DATE", ParentStatus.SHIPPED, "On the way",
        "Your order is on the way.",
    ),
    # ---- Delivered (lowest priority) ----
    ReasonCode(
        "DELIVERED_OHS_RC49", ParentStatus.DELIVERED, "Complete",
        "Your order was delivered.",
    ),
    # ---- Authorization / prescriber ----
    ReasonCode(
        "PA_REQUIRED_RC68", ParentStatus.NOT_FILLED, "Authorization required",
        "This prescription needs a prior authorization before it can be filled.",
    ),
    ReasonCode(
        "PA_CONTACTED_RC70_72", ParentStatus.DELAYED, "Authorization required",
        "We've contacted your prescriber about a required authorization.",
    ),
    ReasonCode(
        "DELAYED_PRESCRIBER_CONTACTED_PA_RC99", ParentStatus.DELAYED, "We need your help",
        "We've contacted your prescriber about this prescription.",
    ),
    # ---- Cancellations (informational) ----
    ReasonCode("CANCELED_RC23", ParentStatus.NOT_FILLED, "Canceled", "This order was canceled."),
    ReasonCode("CANCELED_BY_MEMBER_RC24", ParentStatus.NOT_FILLED, "Canceled",
               "This order was canceled at your request."),
    ReasonCode("CANCELED_MED_NOT_COVERED_RC17", ParentStatus.NOT_FILLED, "Medication not covered",
               "This medication isn't covered under your plan."),
    ReasonCode("CANCELED_PRESCRIBER_DENIED_RC20", ParentStatus.NOT_FILLED, "Prescriber denied",
               "Your prescriber denied this prescription."),
    ReasonCode("CANCELED_RETURNED_RC26", ParentStatus.NOT_FILLED, "Returned",
               "This order was returned."),
    # ---- Scheduled / future ----
    ReasonCode("FUTURE_FILL_RC60", ParentStatus.WORKING_ON_IT, "Scheduled",
               "This prescription is scheduled for a future fill."),
    ReasonCode("FUTURE_FILL_TOO_SOON_RC58_59", ParentStatus.WORKING_ON_IT, "Scheduled",
               "It's too soon to refill this prescription; it's scheduled for later."),
    ReasonCode("RENEWAL_NO_FILLS_RC83", ParentStatus.NOT_FILLED, "Pending",
               "This prescription needs to be renewed.", (SelfServeOption.GO_TO_REFILL,),
               "Request renewal", go_to_refill=True),
    # ---- Suppressed statuses (never surfaced to the member) ----
    ReasonCode("FASTSTART_2_REQUEST_SENT", ParentStatus.WORKING_ON_IT, "Pending",
               "", suppress=True),
    ReasonCode("ORDER_RECEIVED_RC56", ParentStatus.WORKING_ON_IT, "Pending",
               "", suppress=True),
)

# Index for O(1) lookup.
CATALOG: dict[str, ReasonCode] = {rc.code: rc for rc in _CATALOG}


def lookup(status_code: str | None) -> ReasonCode | None:
    """Return the ReasonCode for a status code, or None if unknown.

    Args:
        status_code: Raw status code from the order API.

    Returns:
        The matching ReasonCode, or None when the code is unmapped (caller
        should treat unmapped codes as a low-information "check back later").
    """
    if not status_code:
        return None
    return CATALOG.get(status_code.strip())


def priority_rank(rc: ReasonCode | None) -> int:
    """Compute presentation priority for a resolved status.

    Priority tiers (shared across chat and voice):
        1. Self-serve holds requiring member action.
        2. Ready for pickup.
        3. Everything else.
        4. Delivered.

    Args:
        rc: Resolved reason code, or None for unmapped statuses.

    Returns:
        Integer rank; lower sorts first.
    """
    if rc is None:
        return PRIORITY_EVERYTHING_ELSE
    if rc.self_serve and rc.status == "We need your help":
        return PRIORITY_SELF_SERVE
    if rc.status == "Ready for pickup":
        return PRIORITY_READY_PICKUP
    if rc.parent_status is ParentStatus.DELIVERED:
        return PRIORITY_DELIVERED
    return PRIORITY_EVERYTHING_ELSE
