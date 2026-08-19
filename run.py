#!/usr/bin/env python3
"""Reproduce the results table from a clean clone.

    python3 run.py

This is the definition of done: one command, from a fresh checkout, to the
published table. Every stage fails loudly rather than degrading — a silent
partial run produces a plausible-looking table over incomplete data, which
is worse than a crash.

Stages:
  1. assert the toolchain and SDK match config/pins.toml
  2. derive ground truth from the SDK on disk
  3. baseline the scaffold at zero warnings
  4. generate samples through the pinned gateway
  5. score against the frozen metrics
  6. write a dated results file
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


def step(n: int, total: int, label: str) -> None:
    print(f"\n\033[1m[{n}/{total}] {label}\033[0m")


def run(cmd: list[str], *, why: str) -> None:
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    if proc.returncode != 0:
        raise SystemExit(
            f"\nFAILED: {' '.join(cmd)}\n"
            f"  {why}\n"
            f"  Stopping rather than continuing on partial data."
        )


def main() -> int:
    ap = argparse.ArgumentParser(prog="run.py")
    ap.add_argument("--split", choices=["published", "heldout", "all"], default="all",
                    help="which prompts to score (default: all available locally)")
    ap.add_argument("--models", help="comma-separated subset of the pinned roster")
    ap.add_argument("--limit", type=int, help="samples per prompt (default: pins)")
    ap.add_argument("--skip-generate", action="store_true",
                    help="score samples already on disk without calling any model")
    ap.add_argument("--dry-run", action="store_true", help="plan only")
    args = ap.parse_args()

    total = 5 if args.skip_generate else 6
    n = 0

    n += 1; step(n, total, "Verifying pins")
    from groundtruth.sdk import load_pins, sdk_path, xcode_build, PinMismatch
    pins = load_pins()
    try:
        build, sdk = xcode_build(pins), sdk_path(pins)
    except PinMismatch as exc:
        raise SystemExit(f"\nFAILED: {exc}")
    print(f"  Xcode {build}  SDK {pins['sdk']['sdk_version']}  target iOS "
          f"{pins['target']['deployment_target']}")
    print(f"  {sdk}")

    n += 1; step(n, total, "Deriving ground truth from the SDK")
    run([sys.executable, "-m", "groundtruth"],
        why="Ground truth could not be parsed from the pinned SDK.")

    n += 1; step(n, total, "Baselining the scaffold")
    run([sys.executable, "tests/test_scaffold.py"],
        why="The scaffold does not compile clean. Its warnings would be "
            "counted against every model.")

    if not args.skip_generate:
        n += 1; step(n, total, "Generating samples")
        cmd = [sys.executable, "-m", "runner.generate"]
        if args.models: cmd += ["--models", args.models]
        if args.limit:  cmd += ["--limit", str(args.limit)]
        if args.dry_run: cmd += ["--dry-run"]
        run(cmd, why="Generation failed. Check the gateway key and roster ids.")

    if args.dry_run:
        print("\ndry run complete — nothing generated, nothing scored")
        return 0

    n += 1; step(n, total, "Scoring")
    report_path = REPO_ROOT / "build" / "report.json"
    cmd = [sys.executable, "-m", "scoring.score", "--split", args.split,
           "--out", str(report_path)]
    run(cmd, why="Scoring failed.")

    n += 1; step(n, total, "Writing results")
    run([sys.executable, "-m", "scoring.report", "--report", str(report_path)],
        why="Report rendering failed.")

    print("\n\033[1mdone\033[0m — results in results/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
