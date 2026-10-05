"""Authentication tiers and token validation (voice auth model).

Encodes the deterministic parts of the auth stories (TLPDMSF-203/204/246/
372/393/244/209): ANI match to a single family, Level 1.5 step-up when PHI/PII
is involved, primary-token collection (member ID or Rx number), DOB
verification with bounded retries, privacy-flag transfer, and caller-type
routing. The LLM never decides whether a caller is authenticated — these rules do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class AuthLevel(str, Enum):
    """Authentication level reached for the current session."""

    NONE = "none"                 # not identified
    ANI_ONLY = "ani_only"         # matched to a family by phone, no PHI yet
    LEVEL_1_5 = "level_1_5"       # primary token + DOB verified (PHI-eligible)


class CallerType(str, Enum):
    """Who is calling — drives routing before any member flow."""

    MEMBER = "member"
    DOCTOR = "doctor"
    PHARMACIST = "pharmacist"


# Intents that require Level 1.5 step-up because they expose PHI/PII.
PHI_INTENTS = {"order_status", "order_action", "refill", "drug_price"}

# Primary plan type codes take precedence over secondary (TLPDMSF-203).
PRIMARY_PLAN_CODES = {1, 2, 3, 4, 5, 14, 15, 16, 17, 18}
SECONDARY_PLAN_CODES = {0, 6, 7, 8, 9, 10, 11, 12, 13}

MAX_DOB_RETRIES = 2  # first failure re-prompts once; then defer/transfer.


@dataclass
class AuthState:
    """Mutable auth progress for a session.

    Attributes:
        level: Current authentication level.
        caller_type: Identified caller type.
        dob_attempts: Count of DOB collection attempts so far.
        privacy_flag: Whether the matched member has a privacy flag (forces
            transfer after authentication).
        token_verified: Whether a primary token (member ID / Rx) was validated.
    """

    level: AuthLevel = AuthLevel.NONE
    caller_type: CallerType = CallerType.MEMBER
    dob_attempts: int = 0
    privacy_flag: bool = False
    token_verified: bool = False


def requires_step_up(intent: str, level: AuthLevel) -> bool:
    """Return True if an intent needs Level 1.5 auth not yet reached.

    Args:
        intent: The routed intent name.
        level: Current auth level.

    Returns:
        Whether step-up authentication must be collected before proceeding.
    """
    return intent in PHI_INTENTS and level is not AuthLevel.LEVEL_1_5


def valid_member_id(token: str) -> bool:
    """Validate a member ID token.

    Member IDs are alphanumeric with a 9-character minimum (TLPDMSF-372).

    Args:
        token: Raw member ID input.

    Returns:
        Whether the token is a structurally valid member ID.
    """
    t = token.strip()
    return len(t) >= 9 and bool(re.fullmatch(r"[A-Za-z0-9]+", t))


def valid_rx_number(token: str) -> bool:
    """Validate a prescription-number token.

    Rx numbers are numeric, 5–12 digits (mail or retail) per TLPDMSF-372/393.

    Args:
        token: Raw Rx number input (a leading ``RX-`` prefix is tolerated).

    Returns:
        Whether the token is a structurally valid Rx number.
    """
    t = token.strip().upper().removeprefix("RX-").removeprefix("RX")
    t = t.lstrip("-")
    return bool(re.fullmatch(r"\d{5,12}", t))


def register_dob_attempt(state: AuthState, success: bool) -> str:
    """Advance the DOB recovery state machine and return the next action.

    Args:
        state: The session auth state (mutated in place).
        success: Whether the member's DOB was successfully captured/matched.

    Returns:
        One of ``"verified"``, ``"reprompt"``, ``"defer"``, or ``"transfer"``.
    """
    if success:
        return "verified"
    state.dob_attempts += 1
    if state.dob_attempts == 1:
        return "reprompt"
    if state.dob_attempts == MAX_DOB_RETRIES:
        return "defer"
    return "transfer"


def route_caller_type(caller_type: CallerType) -> str:
    """Return the routing destination marker for a non-member caller type.

    Args:
        caller_type: The identified caller type.

    Returns:
        A routing marker: ``"member_flow"``, ``"pharmacy_help_desk"``, or
        ``"icm_clinical"`` (doctor/office → clinical routing via ICM).
    """
    if caller_type is CallerType.MEMBER:
        return "member_flow"
    if caller_type is CallerType.PHARMACIST:
        return "pharmacy_help_desk"
    return "icm_clinical"
