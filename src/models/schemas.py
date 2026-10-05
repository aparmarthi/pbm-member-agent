"""Domain models and agent state schema.

Data model mirrors the PBM order structure (schema only — no real member data):

    Member ──< Patient (family plan) ──< Order ──< Prescription

All member-facing identifiers here are synthetic. See ``src/data/synthetic.py``.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Channel(str, Enum):
    """Delivery channel. Drives lookback, pagination, and action behavior."""

    CHAT = "chat"
    VOICE = "voice"


class Prescription(BaseModel):
    """A single prescription line within an order."""

    rx_number: str
    drug_name: str
    status_code: str = Field(description="Raw status code; resolved via reason_codes catalog.")
    condition_code: str | None = Field(
        default=None, description="Refillability code: '0' refillable, '17'/'21' expired, '3' not refillable."
    )
    price: float | None = None


class Order(BaseModel):
    """An order containing one or more prescriptions for a single patient."""

    order_number: str
    order_date: str | None = None
    prescriptions: list[Prescription] = Field(default_factory=list)
    tracking_id: str | None = None
    shipment_address: str | None = None


class Patient(BaseModel):
    """A person on the plan the requester has permission to view (self or family)."""

    internal_id: str
    first_name: str
    last_name: str
    dob: str | None = None
    relationship: Literal["self", "spouse", "child", "dependent"] = "self"
    orders: list[Order] = Field(default_factory=list)


class Member(BaseModel):
    """The authenticated account holder and the patients they can access."""

    member_id: str
    internal_id: str
    patients: list[Patient] = Field(default_factory=list)


# ---- Intent taxonomy (Topic Selector equivalent) ----


class Intent(str, Enum):
    """Top-level routing intents, mirroring Agentforce topics."""

    ORDER_STATUS = "order_status"
    ORDER_ACTION = "order_action"
    REFILL = "refill"
    DRUG_PRICE = "drug_price"
    ESCALATION = "escalation"
    CLOSING = "closing"
    OFF_TOPIC = "off_topic"


class ResolvedStatus(BaseModel):
    """A prescription's status after deterministic reason-code resolution."""

    patient_name: str
    drug_name: str
    status: str
    sub_status: str
    parent_status: str
    order_number: str
    priority: int
    self_serve: list[str] = Field(default_factory=list)
    primary_cta: str | None = None
    escalate: bool = False
    go_to_refill: bool = False
    tracking_id: str | None = None
    price: float | None = None


class RefillCandidate(BaseModel):
    """A prescription evaluated for refill eligibility."""

    patient_name: str
    drug_name: str
    rx_number: str
    condition_code: str | None
    outcome: str
    message: str
    can_add_to_cart: bool = False
    transfer: bool = False
    list_priority: int | None = None
    price: float | None = None


class PriceQuote(BaseModel):
    """A drug price / coverage result."""

    drug_name: str
    covered: bool
    price: float | None = None
    prior_auth_required: bool = False
    message: str = ""
    alternatives: list[str] = Field(default_factory=list)
    needs_disambiguation: bool = False
    disambiguation_options: list[str] = Field(default_factory=list)


class AgentTurnResult(BaseModel):
    """Structured output of one agent turn (the reply plus turn state)."""

    reply: str
    intent: Intent
    escalated: bool = False
    handoff_target: str | None = None
    shown: list[ResolvedStatus] = Field(default_factory=list)
    has_more: bool = False
