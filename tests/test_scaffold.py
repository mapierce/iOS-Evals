"""Scaffold baseline.

INVARIANT: the scaffold compiles at zero warnings and zero errors before any
model output is inserted. Scaffold noise would be counted against every model
and silently pollute every score. Run this before any scoring run.

    python3 tests/test_scaffold.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from groundtruth.sdk import load_pins
from runner.compile import build_source

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        if detail:
            print("\n".join(f"        {ln}" for ln in detail.strip().splitlines()[:20]))
        FAILURES.append(name)


def diag_lines(stderr: str) -> list[str]:
    # Counting only; classification comes from the serialized .dia in scoring.
    return [ln for ln in stderr.splitlines()
            if (": warning:" in ln or ": error:" in ln) and not ln.startswith(" ")]


def main() -> int:
    pins = load_pins()
    print(f"scaffold baseline @ iOS {pins['target']['deployment_target']}, "
          f"SDK {pins['sdk']['sdk_version']}\n")

    # 1. Empty scaffold must be silent.
    empty = build_source("")
    try:
        check("empty scaffold builds", empty.ok, empty.stderr)
        check("empty scaffold emits zero diagnostics",
              len(diag_lines(empty.stderr)) == 0,
              "\n".join(diag_lines(empty.stderr)))
        check("serialized diagnostics produced", len(empty.dia_paths) > 0)
    finally:
        shutil.rmtree(empty.workdir, ignore_errors=True)

    # 2. Positive control: a soft-deprecated symbol MUST warn. If this fails,
    #    -warn-soft-deprecated has stopped working and the benchmark would
    #    silently observe ~14% of deprecations.
    soft = build_source(
        "struct _Probe: View {\n"
        "    var body: some View { Text(\"x\").foregroundColor(.blue) }\n"
        "}"
    )
    try:
        warned = any("foregroundColor" in ln and "warning:" in ln
                     for ln in diag_lines(soft.stderr))
        check("soft-deprecated symbol warns (-warn-soft-deprecated live)",
              warned, soft.stderr)
    finally:
        shutil.rmtree(soft.workdir, ignore_errors=True)

    # 3. Positive control: an above-target symbol MUST fail to build.
    above = build_source(
        "struct _Probe2: View {\n"
        "    var body: some View { Text(\"x\").presentationSizing(.form) }\n"
        "}"
    )
    try:
        check("above-target symbol fails to compile", not above.ok, above.stderr)
    finally:
        shutil.rmtree(above.workdir, ignore_errors=True)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
