"""Held-out split isolation.

INVARIANT: the held-out prompts never appear in any tracked file. Published
prompts get scraped and trained on; the held-out split is the control that
detects it. A held-out task that reaches the public repo is worthless, and
worse, silently so — the numbers still compute, they just stop meaning
anything.

This exists because the split leaked once: the corpus builder held all
fourteen prompts inline, so committing the builder published the four
held-out tasks.

    python3 tests/test_split_isolation.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from groundtruth.sdk import REPO_ROOT

HELD_OUT = REPO_ROOT / "prompts.local" / "heldout.json"
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        if detail:
            print(f"        {detail}")
        FAILURES.append(name)


def tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
    return [REPO_ROOT / line for line in out.splitlines() if line]


def main() -> int:
    print("held-out split isolation\n")

    check("prompts.local/ is gitignored",
          subprocess.run(["git", "check-ignore", "-q", "prompts.local"],
                         cwd=REPO_ROOT).returncode == 0)

    if not HELD_OUT.is_file():
        print("  SKIP  held-out file not present locally; nothing to leak")
        return 0

    held = json.loads(HELD_OUT.read_text())["prompts"]
    ids = [e["id"] for e in held]
    tasks = [e["task"] for e in held]

    leaked_ids, leaked_tasks = [], []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(REPO_ROOT)
        for pid in ids:
            if pid in text:
                leaked_ids.append(f"{rel}: {pid}")
        for task in tasks:
            # Match on a distinctive slice rather than the whole string, so a
            # reformatted or line-wrapped copy is still caught.
            if task[:60] in text:
                leaked_tasks.append(f"{rel}: {task[:40]}...")

    check("no held-out prompt IDs in tracked files", not leaked_ids,
          "\n        ".join(leaked_ids))
    check("no held-out task text in tracked files", not leaked_tasks,
          "\n        ".join(leaked_tasks))
    check("held-out file itself is ignored",
          subprocess.run(["git", "check-ignore", "-q", str(HELD_OUT)],
                         cwd=REPO_ROOT).returncode == 0)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print(f"all checks passed ({len(ids)} held-out prompts isolated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
