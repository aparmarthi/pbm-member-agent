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
from datetime import date, datetime
from enum import Enum

from src.models.schemas import Member


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
MAX_TOKEN_ATTEMPTS = 2  # a second unmatched member ID / Rx number transfers.


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
        token_attempts: Count of unmatched primary-token attempts so far.
        step: Which credential is being collected next: ``"token"`` or ``"dob"``.
        pending_intent: The PHI intent waiting on step-up, resumed once verified.
        pending_input: The member's original request, replayed once verified.
    """

    level: AuthLevel = AuthLevel.NONE
    caller_type: CallerType = CallerType.MEMBER
    dob_attempts: int = 0
    privacy_flag: bool = False
    token_verified: bool = False
    token_attempts: int = 0
    step: str = "token"
    pending_intent: str | None = None
    pending_input: str | None = None


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


def match_token(text: str, member: Member) -> bool:
    """Return True if the utterance contains this member's ID or one of their Rx numbers.

    Digit groups separated by spaces or dashes are joined first, so a spoken
    "403 314 569" matches ``403314569``.

    Args:
        text: Raw member utterance.
        member: The account the session is matched to.

    Returns:
        Whether a structurally valid token in the text belongs to this member.
    """
    rx_numbers = {rx.rx_number for p in member.patients for o in p.orders
                  for rx in o.prescriptions}
    joined = re.sub(r"(?<=\d)[\s-]+(?=\d)", "", text)
    for token in re.findall(r"[A-Za-z0-9-]{5,}", joined):
        if valid_member_id(token) and token.upper() == member.member_id.upper():
            return True
        if valid_rx_number(token) and re.sub(r"\D", "", token) in rx_numbers:
            return True
    return False


_DATE_PATTERN = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|[A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4}"
)
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y")


def parse_dob(text: str) -> date | None:
    """Extract a date of birth from free text.

    Accepts ISO (``1988-01-01``), US numeric (``01/01/1988``), and spelled-out
    (``January 1st, 1988``) forms.

    Args:
        text: Raw member utterance.

    Returns:
        The parsed date, or None if no supported date is present.
    """
    for match in _DATE_PATTERN.findall(text):
        cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)", "", match).replace(",", "")
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    return None


def dob_matches(text: str, member: Member) -> bool:
    """Return True if the utterance contains the DOB of any patient on the account.

    Args:
        text: Raw member utterance.
        member: The account the session is matched to.

    Returns:
        Whether the stated DOB matches a patient the caller may act for.
    """
    dob = parse_dob(text)
    return dob is not None and any(p.dob == dob.isoformat() for p in member.patients)


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
