"""Render a scored report as a dated markdown results file.

    python3 -m scoring.report --report build/report.json

Writes results/<date>-<corpus-hash>.md and never overwrites a prior run: a
results file is a record of one run against one pin set, and rewriting it
would destroy the only evidence of what was actually measured.

Emits a ranking-suppression banner when the corpus is too thin to support
one. Between-prompt variance swamps between-model variance on a small
corpus, and a confident-looking table over noise is the failure mode this
benchmark would be attacked for.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from groundtruth.sdk import REPO_ROOT

RESULTS = REPO_ROOT / "results"
# Below this many published prompts, per-model differences are not separable
# from prompt-to-prompt noise. Derived from the churning-family count: roughly
# 18 SwiftUI families show real deprecation churn, and a family needs 2-3
# prompts before one oddly-worded task stops dominating its score.
MIN_PROMPTS_FOR_RANKING = 40


def fmt(v, spec="{:.2f}") -> str:
    return "—" if v is None else spec.format(v)


def render(report: dict, prompt_count: int) -> str:
    p = report["pins"]
    L: list[str] = []
    L.append(f"# API currency results — {date.today().isoformat()}")
    L.append("")
    L.append("Lower is better for deprecations and availability violations. "
             "Higher is better for currency score.")
    L.append("")

    if prompt_count < MIN_PROMPTS_FOR_RANKING:
        L.append("> [!WARNING]")
        L.append(f"> **Not a ranking.** This run covers {prompt_count} prompt(s), below the "
                 f"{MIN_PROMPTS_FOR_RANKING} needed for between-model differences to exceed "
                 "between-prompt noise. Ordering in this table is not evidence that one model "
                 "is more current than another. Read the per-area breakdown for signal, and "
                 "treat the aggregate as a pipeline check.")
        L.append("")

    L.append("## Pins")
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| SDK | iPhoneOS {p['sdk_version']} |")
    L.append(f"| Xcode build | `{p['xcode_build']}` |")
    L.append(f"| Deployment target | iOS {p['deployment_target']} |")
    L.append(f"| Temperature | {p['temperature']} |")
    L.append(f"| Samples per prompt | {p['samples_per_prompt']} |")
    L.append(f"| Prompts covered | {prompt_count} |")
    L.append(f"| Split | {report['split']} |")
    L.append("")

    L.append("## Per model")
    L.append("")
    L.append("| Model | Gated | Compiles | Deprecations/sample | Availability/sample | Currency | Truncated |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    rows = sorted(report["models"].items(),
                  key=lambda kv: (kv[1]["currency_score"] is None,
                                  -(kv[1]["currency_score"] or 0)))
    for model, b in rows:
        L.append(
            f"| `{model}` | {b['gated_rate']:.2f} | {fmt(b['compile_rate'])} | "
            f"{fmt(b['deprecations_per_sample'])} | {fmt(b['availability_violations_per_sample'])} | "
            f"{fmt(b['currency_score'], '{:.3f}')} | {b.get('truncated_rate', 0):.2f} |"
        )
    L.append("")

    L.append("## Per API area")
    L.append("")
    L.append("A single aggregate hides which areas a model is stale in. "
             "These breakdowns are the more useful and more defensible number.")
    L.append("")
    areas: dict[str, dict[str, dict]] = {}
    for key, b in report["by_area"].items():
        model, area = key.split("|", 1)
        areas.setdefault(area, {})[model] = b
    for area in sorted(areas):
        L.append(f"### {area}")
        L.append("")
        L.append("| Model | Gated | Deprecations/sample | Currency |")
        L.append("|---|---:|---:|---:|")
        for model, b in sorted(areas[area].items(),
                               key=lambda kv: (kv[1]["currency_score"] is None,
                                               -(kv[1]["currency_score"] or 0))):
            L.append(f"| `{model}` | {b['gated_rate']:.2f} | "
                     f"{fmt(b['deprecations_per_sample'])} | "
                     f"{fmt(b['currency_score'], '{:.3f}')} |")
        L.append("")

    L.append("## Method")
    L.append("")
    L.append("Metrics are defined in [`docs/metrics.md`](../docs/metrics.md), frozen before "
             "any result was viewed. Ground truth is parsed from the pinned SDK on disk at "
             "run time and is never hand-maintained. Samples that fail to generate or fail "
             "to compile are retained as failures, never dropped from the denominator.")
    L.append("")
    L.append("The truncated column is the share of samples that stopped at the output "
             "ceiling. Truncated Swift does not compile, so a high value means the "
             "ceiling rather than the model is shaping that row's compile rate.")
    L.append("")
    L.append("Deprecations are counted from the compiler's `DeprecatedDeclaration` "
             "diagnostic group, read from serialized `.dia` output rather than parsed from "
             "human-readable text. Availability violations are attributed by AST inspection "
             "cross-referenced against ground truth, because availability errors carry no "
             "diagnostic group.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(prog="scoring.report")
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "build" / "report.json")
    args = ap.parse_args()

    report = json.loads(args.report.read_text())
    # Coverage actually achieved in THIS run, not the size of the corpus on
    # disk. A results file that reports corpus size overstates what was
    # measured, which is the sort of claim this benchmark exists to avoid.
    prompt_count = len({s["prompt_id"] for s in report["samples"]})
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{date.today().isoformat()}-{report['split']}.md"
    n = 1
    while out.exists():                       # never overwrite a prior run
        n += 1
        out = RESULTS / f"{date.today().isoformat()}-{report['split']}-{n}.md"
    out.write_text(render(report, prompt_count))
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
