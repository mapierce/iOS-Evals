"""Build the prompt corpus from ground-truth-derived families and task text.

    python3 prompts/build_corpus.py

Prompts are derived from ground truth, never recall: prompts/families.py
carries the API families extracted from the @available parse, and every symbol
is asserted against the ground truth artifact before anything is written. A
gate symbol missing from ground truth would silently drop correct answers out
of scoring.

Published tasks live in prompts/tasks.py; the held-out split lives in
gitignored prompts.local/heldout_tasks.json and is merged in only when
present. A stranger cloning the repo builds the published corpus alone, which
is correct — the split is worthless if they can reproduce it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from groundtruth.sdk import REPO_ROOT
from families import FAMILIES
from tasks import TASKS

GROUND_TRUTH = REPO_ROOT / "build" / "groundtruth.json"
PUBLISHED = REPO_ROOT / "prompts" / "corpus.json"
HELD_OUT_TASKS = REPO_ROOT / "prompts.local" / "heldout_tasks.json"
HELD_OUT = REPO_ROOT / "prompts.local" / "heldout.json"


def all_tasks() -> list[tuple[str, str, str]]:
    tasks = [tuple(t) for t in TASKS]
    if HELD_OUT_TASKS.is_file():
        tasks += [tuple(t) for t in json.loads(HELD_OUT_TASKS.read_text())["tasks"]]
    else:
        print(f"note: {HELD_OUT_TASKS.name} absent — building published split only")
    return tasks


def build() -> list[dict]:
    seen: dict[str, int] = {}
    out = []
    for family, split, task in all_tasks():
        spec = FAMILIES[family]
        seen[family] = seen.get(family, 0) + 1
        suffix = "h" if split == "heldout" else ""
        out.append({
            "id": f"{family}-{suffix}{seen[family]:02d}",
            "split": split,
            "api_area": family,
            "task": task,
            "gate_symbols": spec["gate"],
            "stale_markers": spec["stale"],
            "current_markers": spec["current"],
            "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
        })
    return out


def main() -> int:
    if not GROUND_TRUTH.is_file():
        raise SystemExit("build/groundtruth.json missing — run: python3 -m groundtruth")
    known = {s["name"] for s in json.loads(GROUND_TRUTH.read_text())["symbols"]}

    problems: list[str] = []
    for family, spec in FAMILIES.items():
        for field in ("gate", "stale", "current"):
            for sym in spec[field]:
                if sym not in known:
                    problems.append(f"{family}.{field}: {sym!r} not in ground truth")
        if not spec["current"]:
            problems.append(f"{family}: no current markers — cannot reward a correct answer")
        for sym in spec["stale"] + spec["current"]:
            if sym not in spec["gate"]:
                problems.append(f"{family}: {sym!r} is a marker but not a gate symbol")
    if problems:
        print("family validation FAILED:")
        for p in problems:
            print("  " + p)
        return 1

    corpus = build()
    for split, path in (("published", PUBLISHED), ("heldout", HELD_OUT)):
        entries = [e for e in corpus if e["split"] == split]
        if not entries:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "split": split,
            "count": len(entries),
            "families": sorted({e["api_area"] for e in entries}),
            "corpus_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True).encode()).hexdigest(),
            "prompts": entries,
        }, indent=1) + "\n")
        print(f"{split:10} {len(entries):3} prompts across "
              f"{len({e['api_area'] for e in entries}):2} families  "
              f"-> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
