"""Run the eval suites, print a scorecard, and store a timestamped result.

Usage:
    python -m evals.run              # mock provider, hermetic
    LLM_PROVIDER=openrouter python -m evals.run
    python -m evals.run --no-save    # don't write evals/results/

Exits non-zero when any threshold fails, so CI can gate on it. Each run is
compared with the most recent saved result to surface regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.evaluation.harness import run_all

RESULTS = Path(__file__).resolve().parent / "results"


def _previous() -> dict | None:
    runs = sorted(RESULTS.glob("*.json"))
    return json.loads(runs[-1].read_text()) if runs else None


def main() -> None:
    """Run all suites and report."""
    parser = argparse.ArgumentParser(description="PBM agent eval harness")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    previous = _previous()
    report = run_all()
    prev_metrics = previous["metrics"] if previous else {}

    print(f"\nEval run {report['timestamp']}  ·  provider={report['provider']}\n")
    print(f"{'metric':40}{'value':>10}{'vs prev':>10}   threshold")
    for name, value in report["metrics"].items():
        delta = f"{value - prev_metrics[name]:+.3f}" if name in prev_metrics else "—"
        gate = report["thresholds"].get(name)
        verdict = f"{gate['op']} {gate['value']}  {'PASS' if gate['passed'] else 'FAIL'}" if gate else ""
        print(f"{name:40}{value:>10.3f}{delta:>10}   {verdict}")

    if report["failures"]:
        print(f"\n{len(report['failures'])} failing case(s):")
        for f in report["failures"]:
            detail = {k: v for k, v in f.items() if k not in ("suite", "reply")}
            print(f"  [{f['suite']}] {detail}")

    if not args.no_save:
        RESULTS.mkdir(exist_ok=True)
        out = RESULTS / f"{report['timestamp'].replace(':', '')}.json"
        out.write_text(json.dumps(report, indent=2))
        print(f"\nSaved {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    print(f"\nOverall: {'PASS' if report['passed'] else 'FAIL'}\n")
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
