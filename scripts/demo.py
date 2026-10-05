"""Scripted end-to-end demo of the PBM member agent.

Walks eight short acts through the compiled graph — one per design claim in the
README — and prints each reply alongside the state the graph decided on (intent,
escalation, handoff target). Runs on the mock LLM: no keys, no cost, same output
every time.

Usage:
    python -m scripts.demo            # run straight through
    python -m scripts.demo --pause    # wait for Enter between acts (live demos)
"""

from __future__ import annotations

import argparse

from src.data import synthetic
from src.graph.build import build_graph
from src.models.schemas import Channel

# (title, talking point, scenario, channel, is_verified, utterances)
ACTS = [
    ("1. Order status — chat",
     "Statuses derived from the reason-code catalog and rendered by template. "
     "The LLM only picks the intent.",
     "single_patient_mixed_statuses", Channel.CHAT, True, ["Where is my order?"]),
    ("2. Same member, voice channel",
     "Same graph and data. Config changes the lookback window and pagination wording.",
     "single_patient_mixed_statuses", Channel.VOICE, True, ["Where is my order?"]),
    ("3. Family plan",
     "One account holder, three patients. Ranked by priority tier, so the "
     "high-copay approval comes first.",
     "family_plan", Channel.CHAT, True, ["What's the status of my family's prescriptions?"]),
    ("4. Must-transfer hold",
     "A must-transfer hold (RC14) sends the member to a human deterministically. "
     "The model has no say in it.",
     "escalation_required", Channel.CHAT, True, ["Where is my prescription?"]),
    ("5. Refill eligibility engine",
     "Condition codes decide eligibility. The controlled substance (Adderall) and "
     "the too-early fill are excluded; the renewal is listed with a note.",
     "refill_mixed_conditions", Channel.CHAT, True, ["I'd like to refill my meds"]),
    ("6. Drug price — coverage, prior auth, generic alternative",
     "Covered price, prior-auth path, and a lower-cost generic. The agent never "
     "recommends a drug for a condition.",
     "single_patient_mixed_statuses", Channel.CHAT, True,
     ["How much is Lipitor?", "How much does Wegovy cost?"]),
    ("7. Step-up auth before PHI",
     "Unverified session: the auth gate pauses for a token before any PHI intent. "
     "The prompt depends on intent (refill asks for the Rx number first).",
     "family_plan", Channel.VOICE, False, ["Where is my order?", "I need a refill"]),
    ("8. Crisis safety — gate runs before the router",
     "Self-harm language is pinned to escalation before any LLM call. "
     "The reply gives the 988 Lifeline and a warm handoff.",
     "single_patient_mixed_statuses", Channel.CHAT, True,
     ["Honestly I just want to end my life", "This is ridiculous, get me a human"]),
]


def run_turn(graph, member, channel: Channel, is_verified: bool, text: str) -> None:
    """Send one utterance through the graph and print reply plus decision state.

    Args:
        graph: Compiled LangGraph runnable.
        member: Synthetic member loaded into the session.
        channel: Active channel.
        is_verified: Whether the session has already passed step-up auth.
        text: Member utterance.
    """
    result = graph.invoke({
        "user_input": text,
        "channel": channel,
        "member": member,
        "is_verified": is_verified,
        "messages": [("user", text)],
    })
    intent = result.get("intent")
    print(f"\n  member> {text}")
    print("  agent>  " + result["messages"][-1].content.replace("\n", "\n          "))
    print(f"  [intent={intent.value if intent else None} "
          f"escalated={bool(result.get('escalated'))} "
          f"handoff={result.get('handoff_target')}]")


def main() -> None:
    """Run every demo act in order."""
    parser = argparse.ArgumentParser(description="Scripted PBM agent demo")
    parser.add_argument("--pause", action="store_true", help="wait for Enter between acts")
    args = parser.parse_args()

    graph = build_graph()
    for title, point, scenario, channel, verified, utterances in ACTS:
        if args.pause:
            input("\n(press Enter) ")
        print(f"\n{'=' * 78}\n{title}  [{scenario} · {channel.value}]")
        print(f"  -> {point}")
        member = synthetic.build(scenario)
        for text in utterances:
            run_turn(graph, member, channel, verified, text)
    print(f"\n{'=' * 78}\nDone. Tests: pytest -q  ·  Interactive: python -m src.serving.cli\n")


if __name__ == "__main__":
    main()
