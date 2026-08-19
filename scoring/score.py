"""Score generated samples against the five frozen metrics.

    python3 -m scoring.score [--split published] [--out results/...]

Definitions are frozen in docs/metrics.md and are not re-derived here. In
particular the functional gate is an AST check on source and does NOT require
the sample to compile: availability violations are hard compile errors, so a
gate tied to a successful build would exclude exactly the samples the
availability metric exists to count.

Deprecations come from the compiler's DeprecatedDeclaration diagnostic group.
Availability violations come from AST plus ground truth, because availability
errors carry no diagnostic group and parsing their prose is forbidden.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import shutil
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from groundtruth.sdk import REPO_ROOT, load_pins
from runner.ast_dump import dump_ast, ASTDumpError
from runner.compile import build_source
from runner.diagnostics import parse_dia
from scoring.references import extract_references

SAMPLES_DIR = REPO_ROOT / "build" / "samples"
GROUND_TRUTH = REPO_ROOT / "build" / "groundtruth.json"
PUBLISHED = REPO_ROOT / "prompts" / "corpus.json"
HELD_OUT = REPO_ROOT / "prompts.local" / "heldout.json"


def version_tuple(v: str) -> tuple[int, ...]:
    out = []
    for chunk in (v or "").split("."):
        try:
            out.append(int(chunk))
        except ValueError:
            out.append(0)
    return tuple(out)


@dataclass
class Scored:
    prompt_id: str
    model: str
    api_area: str
    sample_index: int
    gated: bool
    compiled: bool
    deprecations: int
    availability_violations: int
    relevant_calls: int
    current_calls: int
    error: str | None = None


class GroundTruth:
    def __init__(self, path: Path, target: str):
        gt = json.loads(path.read_text())
        self.target = version_tuple(target)
        self.deprecated: set[str] = set()
        self.introduced: dict[str, tuple[int, ...]] = {}
        for s in gt["symbols"]:
            a = s["availability"]
            if a["deprecated"] or a["deprecated_unspecified"]:
                self.deprecated.add(s["name"])
            if a["introduced"]:
                v = version_tuple(a["introduced"])
                # Keep the EARLIEST introduction across overloads: a symbol is
                # available from its earliest form, so taking the latest would
                # invent violations that the compiler never reports.
                prev = self.introduced.get(s["name"])
                if prev is None or v < prev:
                    self.introduced[s["name"]] = v

    def known(self, name: str) -> bool:
        return name in self.introduced or name in self.deprecated

    def above_target(self, name: str) -> bool:
        v = self.introduced.get(name)
        return v is not None and v > self.target

    def is_current(self, name: str) -> bool:
        return not self.above_target(name) and name not in self.deprecated


def load_prompts() -> dict[str, dict]:
    out = {}
    for path in (PUBLISHED, HELD_OUT):
        if path.is_file():
            for p in json.loads(path.read_text())["prompts"]:
                out[p["id"]] = p
    return out


def score_sample(rec: dict, prompt: dict, gt: GroundTruth) -> Scored:
    base = dict(prompt_id=rec["prompt_id"], model=rec["model"],
                api_area=rec["api_area"], sample_index=rec["sample_index"])
    source = rec.get("swift_source") or ""
    if rec.get("error") or not source.strip():
        # Retained as failure, never dropped from the denominator.
        return Scored(**base, gated=False, compiled=False, deprecations=0,
                      availability_violations=0, relevant_calls=0, current_calls=0,
                      error=rec.get("error") or "empty response")

    try:
        ast = dump_ast(source)
        refs = extract_references(ast)
    except ASTDumpError as exc:
        return Scored(**base, gated=False, compiled=False, deprecations=0,
                      availability_violations=0, relevant_calls=0, current_calls=0,
                      error=f"ast: {exc}")

    names = [r.name for r in refs]
    gated = any(n in prompt["gate_symbols"] for n in names)
    relevant = [n for n in names if gt.known(n)]
    current = [n for n in relevant if gt.is_current(n)]
    violations = [n for n in relevant if gt.above_target(n)]

    result = build_source(source)
    try:
        diags = []
        for p in result.dia_paths:
            diags += parse_dia(p)
        deprecations = sum(1 for d in diags
                           if d.is_warning and d.group == "DeprecatedDeclaration")
    finally:
        shutil.rmtree(result.workdir, ignore_errors=True)

    return Scored(**base, gated=gated, compiled=result.ok,
                  deprecations=deprecations, availability_violations=len(violations),
                  relevant_calls=len(relevant), current_calls=len(current))


def aggregate(scored: list[Scored]) -> dict:
    """Metrics per model, then per (model, api_area). Definitions: docs/metrics.md."""
    def block(rows: list[Scored]) -> dict:
        gated = [r for r in rows if r.gated]
        total_rel = sum(r.relevant_calls for r in gated)
        total_cur = sum(r.current_calls for r in gated)
        return {
            "samples": len(rows),
            "gated": len(gated),
            "gated_rate": round(len(gated) / len(rows), 4) if rows else 0.0,
            "compile_rate": round(sum(r.compiled for r in gated) / len(gated), 4) if gated else None,
            "deprecations_per_sample": round(statistics.mean(r.deprecations for r in gated), 4) if gated else None,
            "availability_violations_per_sample": round(statistics.mean(r.availability_violations for r in gated), 4) if gated else None,
            "currency_score": round(total_cur / total_rel, 4) if total_rel else None,
        }

    by_model: dict[str, list[Scored]] = defaultdict(list)
    by_model_area: dict[tuple[str, str], list[Scored]] = defaultdict(list)
    for r in scored:
        by_model[r.model].append(r)
        by_model_area[(r.model, r.api_area)].append(r)

    return {
        "models": {m: block(rows) for m, rows in sorted(by_model.items())},
        # Per-family breakdown. A single aggregate hides which API areas a model
        # is stale in, and is far easier to attack.
        "by_area": {f"{m}|{a}": block(rows) for (m, a), rows in sorted(by_model_area.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="scoring.score")
    ap.add_argument("--split", choices=["published", "heldout", "all"], default="all")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workers", type=int, default=8,
                    help="parallel compiles; each sample builds in its own temp dir")
    args = ap.parse_args()

    pins = load_pins()
    gt = GroundTruth(GROUND_TRUTH, pins["target"]["deployment_target"])
    prompts = load_prompts()

    records = []
    for path in sorted(SAMPLES_DIR.rglob("*.json")):
        rec = json.loads(path.read_text())
        if args.split != "all" and rec["split"] != args.split:
            continue
        records.append(rec)
    if not records:
        raise SystemExit("no samples found — run: python3 -m runner.generate")

    print(f"scoring {len(records)} samples at iOS {pins['target']['deployment_target']} "
          f"({args.workers} workers)")
    # Each sample compiles in its own temp directory, so scoring parallelises
    # cleanly. Serially this is ~3.5s per sample, which does not scale.
    scored: list[Scored] = []
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(score_sample, rec, prompts[rec["prompt_id"]], gt): rec
                for rec in records}
        for i, fut in enumerate(futures.as_completed(futs), 1):
            rec = futs[fut]
            try:
                scored.append(fut.result())
            except Exception as exc:                      # noqa: BLE001
                # Retained as a failure rather than dropped from the denominator.
                scored.append(Scored(
                    prompt_id=rec["prompt_id"], model=rec["model"],
                    api_area=rec["api_area"], sample_index=rec["sample_index"],
                    gated=False, compiled=False, deprecations=0,
                    availability_violations=0, relevant_calls=0, current_calls=0,
                    error=f"scoring: {exc}"))
            if i % 50 == 0 or i == len(records):
                print(f"  {i}/{len(records)}")

    report = {
        "pins": {
            "sdk_version": pins["sdk"]["sdk_version"],
            "xcode_build": pins["toolchain"]["xcode_build"],
            "deployment_target": pins["target"]["deployment_target"],
            "temperature": pins["generation"]["temperature"],
            "samples_per_prompt": pins["generation"]["samples_per_prompt"],
        },
        "split": args.split,
        "sample_count": len(scored),
        **aggregate(scored),
        "samples": [vars(s) for s in scored],
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1) + "\n")
        print(f"wrote {args.out.relative_to(REPO_ROOT)}")

    print(f"\n{'model':34} {'gated':>6} {'compile':>8} {'depr':>6} {'avail':>6} {'currency':>9}")
    for m, b in report["models"].items():
        f = lambda v, s="{:.2f}": "  -  " if v is None else s.format(v)
        print(f"{m:34} {b['gated_rate']:>6.2f} {f(b['compile_rate']):>8} "
              f"{f(b['deprecations_per_sample']):>6} {f(b['availability_violations_per_sample']):>6} "
              f"{f(b['currency_score'], '{:.3f}'):>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
