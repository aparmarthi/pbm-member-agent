"""Scripted end-to-end demo of the PBM member agent.

Each act is one multi-turn conversation (one checkpointed session), chosen to
show one design claim from the README. Every reply is printed with the state
the graph decided on (intent, escalation, handoff target). It runs on the mock
LLM, so it needs no keys, costs nothing, and prints the same output every time.

Usage:
    python -m scripts.demo            # run straight through
    python -m scripts.demo --pause    # wait for Enter between acts (live demos)
"""

from __future__ import annotations

import argparse
from datetime import date

from src.models.schemas import Channel
from src.serving.session import AgentSession

# (title, talking point, scenario, channel, is_verified, utterances)
# Utterances may use {member_id} / {dob}, filled from the synthetic member.
ACTS = [
    ("1. Order status — chat, with follow-up",
     "Statuses come from the reason-code catalog and are rendered by template. "
     "'See more' is resolved by code from the offer the agent made, not by the LLM.",
     "single_patient_mixed_statuses", Channel.CHAT, True,
     ["Where is my order?", "see more"]),
    ("2. Same member, voice channel",
     "Same graph and data. Config narrows the lookback to 10 days (4 orders, not 5) "
     "and switches the pagination to spoken wording.",
     "single_patient_mixed_statuses", Channel.VOICE, True,
     ["Where is my order?", "yes"]),
    ("3. Nothing recent — offer a wider search",
     "No orders in the 45-day chat window, so the agent offers a 6-month search "
     "instead of a dead end.",
     "older_orders_only", Channel.CHAT, True, ["Where's my order?", "yes please"]),
    ("4. Family plan",
     "One account holder, three patients. Ranked by priority tier, so the "
     "high-copay approval comes first.",
     "family_plan", Channel.CHAT, True, ["What's the status of my family's prescriptions?"]),
    ("5. Must-transfer hold",
     "A must-transfer hold (RC14) sends the member to a human deterministically. "
     "The agent doesn't ask 'anything else?' before handing off.",
     "escalation_required", Channel.CHAT, True, ["Where is my prescription?"]),
    ("6. Refill eligibility engine",
     "Condition codes decide eligibility. The controlled substance and too-early fill "
     "are excluded. 'Yes' goes straight to the add-to-cart action.",
     "refill_mixed_conditions", Channel.CHAT, True, ["I'd like to refill my meds", "yes"]),
    ("7. Drug price — coverage, prior auth, follow-up",
     "Covered price and a lower-cost generic. For a PA drug, the cost is offered, "
     "not volunteered. The agent never recommends a drug for a condition.",
     "single_patient_mixed_statuses", Channel.CHAT, True,
     ["How much is Lipitor?", "How much does Wegovy cost?", "yes"]),
    ("8. Step-up auth across turns",
     "Unverified voice caller. The gate parks the request and collects a member ID "
     "and DOB, matched in code (never sent to the LLM). Then it answers the "
     "original question.",
     "single_patient_mixed_statuses", Channel.VOICE, False,
     ["Where is my order?", "It's {member_id}", "{dob}"]),
    ("9. Crisis safety — even mid-authentication",
     "Self-harm language is pinned to escalation before any LLM call, including "
     "while a credential prompt is pending. The reply gives the 988 Lifeline.",
     "family_plan", Channel.VOICE, False,
     ["I need a refill", "Honestly I just want to end my life"]),
]


def run_act(scenario: str, channel: Channel, verified: bool, utterances: list[str]) -> None:
    """Play one conversation and print each reply with the graph's decisions.

    Args:
        scenario: Synthetic member scenario name.
        channel: Active channel.
        verified: Whether the session starts already authenticated.
        utterances: Member turns, optionally templated with {member_id} / {dob}.
    """
    session = AgentSession(scenario, channel, verified=verified)
    fill = {"member_id": session.member.member_id,
            "dob": date.fromisoformat(session.member.patients[0].dob).strftime("%B %-d, %Y")}
    for template in utterances:
        text = template.format(**fill)
        turn = session.send(text)
        print(f"\n  member> {text}")
        print("  agent>  " + turn.reply.replace("\n", "\n          "))
        print(f"  [intent={turn.intent.value} escalated={turn.escalated} "
              f"handoff={turn.handoff_target}]")


def main() -> None:
    """Run every demo act in order."""
    parser = argparse.ArgumentParser(description="Scripted PBM agent demo")
    parser.add_argument("--pause", action="store_true", help="wait for Enter between acts")
    args = parser.parse_args()

    for title, point, scenario, channel, verified, utterances in ACTS:
        if args.pause:
            input("\n(press Enter) ")
        print(f"\n{'=' * 78}\n{title}  [{scenario} · {channel.value}]")
        print(f"  -> {point}")
        run_act(scenario, channel, verified, utterances)
    print(f"\n{'=' * 78}\nDone. Tests: pytest -q  ·  Evals: python -m evals.run  ·  "
          f"UI: streamlit run src/serving/dashboard.py\n")


if __name__ == "__main__":
    main()
