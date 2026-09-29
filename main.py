"""Entry point for FairLens — Explainable Resume Screening & Hiring Blind-Spot Analyzer.

    python main.py            start the web interface (Streamlit)
    python main.py --summary  print a screening audit summary in the terminal
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def launch_ui() -> int:
    """Start Streamlit with the app script; returns its exit code."""
    command = [
        sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "ui" / "app.py"),
        # Headless: without it Streamlit's first run stops to ask for an email address.
        "--server.headless", "true",
    ]
    try:
        return subprocess.call(command, cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        return 0


def print_summary() -> int:
    """Run a screening audit over every role and print the results."""
    from modules.audit import AuditEngine
    from modules.data_manager import DataManager

    manager = DataManager(PROJECT_ROOT / "data")
    for message in manager.load_errors.values():
        print(f"[error] {message}")
    for message in manager.skipped_records:
        print(f"[skipped] {message}")

    audit = AuditEngine(manager.baseline, manager.alternative, list(manager.configs.values())).run(manager)
    if audit.empty:
        print("No candidates with a target role yet. Add candidates and roles first.")
        return 0

    s = audit.summary
    print(f"\nFAIRLENS SCREENING AUDIT - {audit.scope}")
    print(f"Baseline: {audit.baseline.name} ({audit.baseline.short_label})")
    print(f"Alternative: {audit.alternative.name} ({audit.alternative.short_label})\n")
    print(f"Candidates analysed      {s['candidates']}")
    print(f"Average baseline score   {s['average_score']:.1f}   (median {s['median_score']:.1f}, "
          f"std {s['score_std']:.1f}, range {s['min_score']:.0f}-{s['max_score']:.0f})")
    print(f"Average skill coverage   {s['average_coverage']:.1f}%")
    print(f"High-sensitivity cases   {s['high_sensitivity']}")
    print(f"Potential blind spots    {s['blind_spots']}")
    print(f"Ranking changes          {s['ranking_changes']}")
    print(f"Vocabulary vs evidence   {s['average_vocabulary']:.1f}% exact wording, "
          f"{s['average_evidence']:.1f}% evidence coverage")
    print(f"Potential semantic gaps  {s['semantic_gaps']}\n")

    columns = ["name", "target_role", "baseline_score", "alternative_score", "baseline_rank", "alternative_rank",
               "score_range", "vocabulary_match", "evidence_coverage", "exact_pass_score", "evidence_pass_score",
               "signal"]
    print(audit.table[columns].to_string(index=False))

    print("\nObservations (rule-based, not hiring recommendations):\n")
    for cid, found in audit.observations.items():
        for obs in found:
            print(f"  {manager.candidates[cid].name:<18} {obs.title}: {obs.text}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FairLens — Explainable Resume Screening & Hiring Blind-Spot Analyzer")
    parser.add_argument("--summary", action="store_true", help="print an audit summary instead of opening the UI")
    args = parser.parse_args()
    return print_summary() if args.summary else launch_ui()


if __name__ == "__main__":
    sys.exit(main())
