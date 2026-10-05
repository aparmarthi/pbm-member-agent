"""Interactive CLI runner — the quickest way to see the agent work.

Usage:
    python -m src.serving.cli --scenario family_plan --channel chat
    python -m src.serving.cli --channel voice --unverified   # step-up auth flow

Loads a synthetic member into a multi-turn session and runs a REPL through the
compiled graph. Uses the env-selected LLM provider (default: mock, so it runs
with zero keys/cost).
"""

from __future__ import annotations

import argparse

from src.data import synthetic
from src.models.schemas import Channel
from src.serving.session import AgentSession


def main() -> None:
    """Run the interactive CLI."""
    parser = argparse.ArgumentParser(description="PBM member agent CLI")
    parser.add_argument("--scenario", default="single_patient_mixed_statuses",
                        choices=sorted(synthetic.SCENARIOS))
    parser.add_argument("--channel", default="chat", choices=[c.value for c in Channel])
    parser.add_argument("--unverified", action="store_true",
                        help="start unauthenticated (member ID / Rx number, then DOB)")
    args = parser.parse_args()

    session = AgentSession(args.scenario, Channel(args.channel), verified=not args.unverified)
    print(f"Loaded scenario '{args.scenario}' on {args.channel}. "
          f"Type a message (Ctrl-C to exit).")
    if args.unverified:
        print(f"(synthetic credentials — member ID: {session.member.member_id}, "
              f"DOB: {session.member.patients[0].dob})")
    print()
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return
        if not user_input:
            continue
        turn = session.send(user_input)
        print(f"agent> {turn.reply}")
        if turn.escalated:
            print(f"       [handed off → {turn.handoff_target}]")
        print()


if __name__ == "__main__":
    main()
