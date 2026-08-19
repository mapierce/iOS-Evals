"""Diagnostic capture.

Diagnostics are read from the serialized .dia bitstream, never by regex over
human-readable compiler text. These cases pin the decoding against real builds.

    python3 tests/test_diagnostics.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.compile import build_source
from runner.diagnostics import parse_dia, SEVERITY

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        if detail:
            print("\n".join(f"        {ln}" for ln in detail.strip().splitlines()[:12]))
        FAILURES.append(name)


def diags(source: str):
    r = build_source(source)
    out = []
    for p in r.dia_paths:
        out += parse_dia(p)
    shutil.rmtree(r.workdir, ignore_errors=True)
    return r.ok, out


def main() -> int:
    print("diagnostic capture\n")

    # Regression: Swift writes clang's SerializedDiagnostics.h Level enum, not
    # DiagnosticsEngine::Level. Confusing them reports every warning as a
    # remark, which would zero out the deprecation metric.
    check("serialized severity enum ordering",
          SEVERITY[2] == "warning" and SEVERITY[5] == "remark")

    ok, ds = diags(
        'struct _D: View {\n'
        '    var body: some View {\n'
        '        NavigationView { Text("x").foregroundColor(.blue) }\n'
        '    }\n'
        '}'
    )
    warns = [d for d in ds if d.is_warning]
    check("deprecated code still builds", ok)
    check("two deprecations captured", len(warns) == 2,
          "\n".join(f"{d.severity} {d.message}" for d in ds))
    check("deprecations carry DeprecatedDeclaration group",
          all(d.group == "DeprecatedDeclaration" for d in warns),
          "\n".join(repr(d.group) for d in warns))
    check("source location decoded",
          all(d.line > 0 and d.column > 0 and d.filename.endswith(".swift")
              for d in warns))

    ok, ds = diags(
        'struct _A: View {\n'
        '    var body: some View { Text("x").presentationSizing(.form) }\n'
        '}'
    )
    errs = [d for d in ds if d.is_error]
    check("above-target code fails to build", not ok)
    check("availability errors captured", len(errs) >= 1,
          "\n".join(f"{d.severity} {d.message}" for d in ds))
    # Documented limitation: availability errors carry no diagnostic group, so
    # they cannot be classified from the .dia alone. Attribution comes from AST
    # plus ground truth. If Swift ever starts grouping them, revisit scoring.
    check("availability errors carry no group (known limitation)",
          all(d.group == "" for d in errs),
          "\n".join(repr(d.group) for d in errs))

    ok, ds = diags(
        'struct _C: View {\n'
        '    var body: some View { NavigationStack { Text("x").foregroundStyle(.blue) } }\n'
        '}'
    )
    check("current-API code is diagnostic-free",
          ok and not [d for d in ds if d.is_warning or d.is_error],
          "\n".join(f"{d.severity} {d.message}" for d in ds))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
