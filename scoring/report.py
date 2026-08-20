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
    L.append("> [!IMPORTANT]")
    L.append("> **Currency is a rate, not a verdict.** It is scale-invariant: a verbose "
             "model that is proportionally just as wrong scores the same as a concise one "
             "that is wrong far less often. Read it next to *stale calls/sample*, which is "
             "how much there actually is to fix in a file. Rows are ordered by currency for "
             "readability only — see the confidence intervals below before reading order as "
             "ranking.")
    L.append("")
    L.append("| Model | Gated | Compiles | Depr/sample | Avail/sample | Relevant/sample | Stale/sample | Currency | Truncated |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = sorted(report["models"].items(),
                  key=lambda kv: (kv[1]["currency_score"] is None,
                                  -(kv[1]["currency_score"] or 0)))
    for model, b in rows:
        L.append(
            f"| `{model}` | {b['gated_rate']:.2f} | {fmt(b['compile_rate'])} | "
            f"{fmt(b['deprecations_per_sample'])} | {fmt(b['availability_violations_per_sample'])} | "
            f"{fmt(b.get('relevant_calls_per_sample'), '{:.1f}')} | "
            f"{fmt(b.get('stale_calls_per_sample'), '{:.2f}')} | "
            f"{fmt(b['currency_score'], '{:.3f}')} | {b.get('truncated_rate', 0):.2f} |"
        )
    L.append("")

    # Confidence intervals, and which adjacent pairs are actually separated.
    cis = [(m, b["currency_score"], b.get("currency_ci")) for m, b in rows
           if b.get("currency_ci") and b["currency_score"] is not None]
    if cis:
        L.append("### Is the order meaningful?")
        L.append("")
        L.append("95% confidence intervals, bootstrapped over **prompts** rather than "
                 "samples: k draws of one prompt at a fixed temperature are highly "
                 "correlated, so resampling samples would understate uncertainty.")
        L.append("")
        L.append("| Model | Currency | 95% CI | Prompts |")
        L.append("|---|---:|---|---:|")
        for m, c, (lo, hi, n) in cis:
            L.append(f"| `{m}` | {c:.3f} | [{lo:.3f}, {hi:.3f}] | {n} |")
        L.append("")
        overlaps = []
        for i in range(len(cis) - 1):
            (ma, _, (loa, _, _)), (mb, _, (_, hib, _)) = cis[i], cis[i + 1]
            overlaps.append((ma, mb, loa <= hib))
        n_over = sum(1 for *_, o in overlaps if o)
        L.append(f"**{n_over} of {len(overlaps)} adjacent pairs have overlapping intervals** "
                 "and are not distinguishable at this sample size. Treat the table as tiers, "
                 "not a leaderboard:")
        L.append("")
        for ma, mb, o in overlaps:
            mark = "overlap — not distinguishable" if o else "**separated**"
            L.append(f"- `{ma.split('/')[-1]}` vs `{mb.split('/')[-1]}` — {mark}")
        L.append("")

    L.append("## Per API area")
    L.append("")
    L.append("A single aggregate hides which areas a model is stale in. "
             "These breakdowns are the more useful and more defensible number.")
    L.append("")
    L.append("**Read the gated column first.** A low value does not mean the model "
             "failed — it means the model solved the task without touching the API "
             "area under test, typically by hand-rolling the behaviour. That is a "
             "finding in itself, but it also means the currency figure on that row "
             "rests on very few samples and should not be compared across models.")
    L.append("")
    areas: dict[str, dict[str, dict]] = {}
    for key, b in report["by_area"].items():
        model, area = key.split("|", 1)
        areas.setdefault(area, {})[model] = b
    for area in sorted(areas):
        gates = [b["gated_rate"] for b in areas[area].values()]
        mean_gate = sum(gates) / len(gates) if gates else 0.0
        L.append(f"### {area}")
        L.append("")
        if mean_gate < 0.25:
            L.append(f"> Mean gate rate {mean_gate:.2f} — models mostly solved these "
                     "tasks without using the API area under test. Currency figures "
                     "below rest on a small minority of samples.")
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

    L.append("## Threats to validity")
    L.append("")
    L.append("Known ways these numbers could mislead, stated so a reader does not have to "
             "find them independently.")
    L.append("")
    L.append("- **Currency rewards verbosity.** It is a ratio over all SwiftUI symbols a "
             "model wrote, and most of those (`Text`, `VStack`, `Spacer`) can never be "
             "stale. A model that writes more boilerplate dilutes its own mistakes. Compare "
             "*stale calls/sample* to see the absolute burden.")
    L.append("- **The gate selects the sample.** Only samples exercising the API area are "
             "scored. If a model hand-rolls when unsure and uses the platform API when "
             "confident, its currency is computed on its confident cases and is optimistic. "
             "A low gate rate makes this worse — read the gated column alongside every "
             "score.")
    L.append("- **Samples within a prompt are correlated.** Five draws at temperature 0.2 "
             "on one task are not five independent observations, which is why the intervals "
             "above resample prompts rather than samples.")
    L.append("- **Ground truth covers SwiftUI and SwiftUICore only.** UIKit interop, "
             "Combine, Observation and Charts calls are invisible, so a model leaning on "
             "them is measured on less of its output.")
    L.append("- **Property wrappers are invisible.** `@State`, `@StateObject`, `@Bindable` "
             "and protocol conformances do not appear in the parse-only AST, so they are "
             "never counted. Two API families were dropped for this reason.")
    L.append("- **Occurrences, not decisions.** Using one deprecated symbol five times "
             "counts five times. That reflects remediation effort, not five separate bad "
             "choices.")
    L.append("- **One SDK, one deployment target.** Valid only at the pins above. A model "
             "scoring well at iOS 17.0 is not thereby current at any other target.")
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
