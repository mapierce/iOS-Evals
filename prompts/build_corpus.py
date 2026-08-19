"""Define the prompt corpus and split it into published / held-out files.

Run from the repo root:

    python3 prompts/build_corpus.py

Tasks describe an OUTCOME and never name a SwiftUI API. That is the whole
design: a 2021 answer and a 2026 answer must both be reachable from the
wording, so the model's choice is the measurement. A task that says "use
NavigationStack" measures nothing.

Every symbol referenced here is asserted against the ground truth artifact
before anything is written. A gate symbol absent from ground truth would
silently exclude correct answers from scoring.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from groundtruth.sdk import REPO_ROOT

GROUND_TRUTH = REPO_ROOT / "build" / "groundtruth.json"
PUBLISHED = REPO_ROOT / "prompts" / "corpus.json"
HELD_OUT = REPO_ROOT / "prompts.local" / "heldout.json"

# split: "published" ships in git; "heldout" stays local so it cannot be
# trained on. Both score through identical machinery.
# Published prompts only. The held-out split lives in a gitignored file and is
# merged in below when present — it must never appear in tracked source, since
# anything committed can be scraped and trained on, which is what the split
# exists to detect.
HELDOUT_SOURCE = REPO_ROOT / "prompts.local" / "heldout_source.json"

CORPUS = [
    {
        "id": "nav-001", "split": "published", "api_area": "navigation",
        "task": "Write a SwiftUI view for an iOS app showing a list of recipe "
                "names. Tapping a recipe opens a detail screen showing that "
                "recipe's name and ingredients.",
        "gate_symbols": ["NavigationView", "NavigationStack", "NavigationLink",
                         "navigationDestination", "NavigationSplitView"],
        "stale_markers": ["NavigationView"],
        "current_markers": ["NavigationStack", "navigationDestination"],
    },
    {
        "id": "nav-002", "split": "published", "api_area": "navigation",
        "task": "Write a SwiftUI screen with the heading 'Inbox' shown in the "
                "navigation bar, and a compose button in the top-right of that bar.",
        "gate_symbols": ["navigationBarTitle", "navigationTitle", "toolbar",
                         "ToolbarItem", "NavigationView", "NavigationStack"],
        "stale_markers": ["navigationBarTitle", "NavigationView"],
        "current_markers": ["navigationTitle", "ToolbarItem", "NavigationStack"],
    },
    {
        "id": "style-001", "split": "published", "api_area": "styling",
        "task": "Write a SwiftUI view showing a temperature reading where the "
                "number is tinted red when it is above 30 degrees and blue otherwise.",
        "gate_symbols": ["foregroundColor", "foregroundStyle"],
        "stale_markers": ["foregroundColor"],
        "current_markers": ["foregroundStyle"],
    },
    {
        "id": "a11y-001", "split": "published", "api_area": "accessibility",
        "task": "Write a SwiftUI toolbar row of three icon-only buttons — share, "
                "favourite, delete — that a VoiceOver user can identify correctly.",
        "gate_symbols": ["accessibility", "accessibilityLabel", "accessibilityAddTraits"],
        "stale_markers": ["accessibility"],
        "current_markers": ["accessibilityLabel", "accessibilityAddTraits"],
    },
    {
        "id": "toolbar-001", "split": "published", "api_area": "toolbar",
        "task": "Write a SwiftUI screen whose navigation bar has a solid dark "
                "background with light text, rather than the system default.",
        "gate_symbols": ["toolbar", "toolbarBackground", "toolbarColorScheme", "ToolbarItem"],
        "stale_markers": ["toolbarBackground"],
        "current_markers": ["toolbarColorScheme", "ToolbarItem"],
    },
    {
        "id": "scroll-001", "split": "published", "api_area": "scrolling",
        "task": "Write a SwiftUI horizontal carousel of cards that comes to rest "
                "with one card centred, rather than stopping between cards.",
        "gate_symbols": ["ScrollView", "scrollTargetBehavior", "scrollTargetLayout",
                         "scrollPosition", "LazyHStack"],
        "stale_markers": [],
        "current_markers": ["scrollTargetBehavior", "scrollTargetLayout"],
    },
    {
        "id": "obs-001", "split": "published", "api_area": "observation",
        "task": "Write a SwiftUI counter screen where the count lives in a separate "
                "model type, and the view updates whenever the model changes.",
        "gate_symbols": ["ObservedObject", "StateObject", "State", "Bindable"],
        "stale_markers": ["ObservedObject"],
        "current_markers": ["State", "Bindable"],
    },
    {
        "id": "sheet-001", "split": "published", "api_area": "presentation",
        "task": "Write a SwiftUI view with a button that slides up a panel covering "
                "the bottom half of the screen, which the user can drag to full height.",
        "gate_symbols": ["sheet", "presentationDetents", "presentationDragIndicator"],
        "stale_markers": [],
        "current_markers": ["presentationDetents", "presentationDragIndicator"],
    },
    {
        "id": "list-001", "split": "published", "api_area": "list",
        "task": "Write a SwiftUI list of tasks grouped under 'Today' and 'Later', "
                "where swiping a row sideways reveals a delete action.",
        "gate_symbols": ["List", "ForEach", "Section", "swipeActions", "listRowSeparator"],
        "stale_markers": [],
        "current_markers": ["swipeActions", "Section"],
    },
    {
        "id": "change-001", "split": "published", "api_area": "onchange",
        "task": "Write a SwiftUI search field that runs a lookup whenever the text "
                "the user has typed changes.",
        "gate_symbols": ["onChange", "task", "onAppear", "State"],
        "stale_markers": [],
        "current_markers": ["onChange"],
    },

]


def load_corpus() -> list[dict]:
    """Published prompts, plus the held-out split when it is present locally.

    A stranger cloning the repo builds the published corpus only. That is
    correct: they cannot reproduce the held-out numbers, and the split would
    be worthless if they could.
    """
    corpus = list(CORPUS)
    if HELDOUT_SOURCE.is_file():
        corpus += json.loads(HELDOUT_SOURCE.read_text())["prompts"]
    else:
        print(f"note: {HELDOUT_SOURCE.name} not present — building published split only")
    return corpus


def main() -> int:
    if not GROUND_TRUTH.is_file():
        raise SystemExit("build/groundtruth.json missing — run: python3 -m groundtruth")
    gt = json.loads(GROUND_TRUTH.read_text())
    known = {s["name"] for s in gt["symbols"]}

    # Assert before writing. A gate symbol missing from ground truth would
    # silently drop correct answers out of scoring.
    problems: list[str] = []
    corpus = load_corpus()

    for e in corpus:
        for field in ("gate_symbols", "stale_markers", "current_markers"):
            for sym in e[field]:
                if sym not in known:
                    problems.append(f"{e['id']}.{field}: {sym!r} not in ground truth")
        if not e["current_markers"]:
            problems.append(f"{e['id']}: no current_markers — cannot reward a correct answer")
        if not e["gate_symbols"]:
            problems.append(f"{e['id']}: no gate_symbols — nothing to gate on")
        for sym in e["stale_markers"] + e["current_markers"]:
            if sym not in e["gate_symbols"]:
                problems.append(f"{e['id']}: {sym!r} is a marker but not a gate symbol")
    if problems:
        print("corpus validation FAILED:")
        for p in problems:
            print("  " + p)
        return 1

    for e in corpus:
        e["task_sha256"] = hashlib.sha256(e["task"].encode()).hexdigest()

    for split, path in (("published", PUBLISHED), ("heldout", HELD_OUT)):
        entries = [e for e in corpus if e["split"] == split]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "split": split,
            "count": len(entries),
            "corpus_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True).encode()
            ).hexdigest(),
            "prompts": entries,
        }
        path.write_text(json.dumps(payload, indent=1) + "\n")
        areas = sorted({e["api_area"] for e in entries})
        print(f"{split:10} {len(entries):2} prompts  {path.relative_to(REPO_ROOT)}")
        print(f"           areas: {', '.join(areas)}")
        print(f"           sha256: {payload['corpus_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
