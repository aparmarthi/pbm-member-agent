"""Interactive CLI runner — the quickest way to see the agent work.

Usage:
    python -m src.serving.cli --scenario family_plan --channel chat

Loads a synthetic member into session context, then runs an interactive REPL
through the compiled graph. Uses the env-selected LLM provider (default: mock,
so it runs with zero keys/cost).
"""

from __future__ import annotations

import argparse

from src.data import synthetic
from src.graph.build import build_graph
from src.models.schemas import Channel


def _last_ai_text(result: dict) -> str:
    """Extract the latest AI message text from a graph result."""
    for msg in reversed(result.get("messages", [])):
        content = getattr(msg, "content", None)
        if content:
            return content
    return "(no reply)"


def main() -> None:
    """Run the interactive CLI."""
    parser = argparse.ArgumentParser(description="PBM member agent CLI")
    parser.add_argument("--scenario", default="single_patient_mixed_statuses",
                        choices=sorted(synthetic.SCENARIOS))
    parser.add_argument("--channel", default="chat", choices=[c.value for c in Channel])
    args = parser.parse_args()

    member = synthetic.build(args.scenario)
    channel = Channel(args.channel)
    graph = build_graph()

    print(f"Loaded scenario '{args.scenario}' on {channel.value}. "
          f"Type a message (Ctrl-C to exit).\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return
        if not user_input:
            continue
        result = graph.invoke({
            "user_input": user_input,
            "channel": channel,
            "member": member,
            "is_verified": True,
            "messages": [("user", user_input)],
        })
        print(f"agent> {_last_ai_text(result)}\n")


if __name__ == "__main__":
    main()
