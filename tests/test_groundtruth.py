"""Ground truth extraction.

Regression cover for parser bugs that are silent by construction: they don't
raise, they just yield fewer symbols, and every downstream metric shifts
without any visible symptom.

    python3 tests/test_groundtruth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from groundtruth.parse_interface import parse_available, _decl_from, _strip_leading_attributes
from groundtruth.sdk import load_pins, interface_paths
from groundtruth.parse_interface import parse_interface

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        if detail:
            print(f"        {detail}")
        FAILURES.append(name)


def main() -> int:
    print("ground truth extraction\n")

    # Declarations commonly begin with attributes. Rejecting any line that
    # starts with "@" as attribute-only dropped ~35% of SwiftUI — every
    # @MainActor view, including NavigationStack, List, and State.
    attributed = "@_Concurrency.MainActor @preconcurrency public struct NavigationStack<Data, Root> : View {"
    check("attribute-prefixed declaration is parsed",
          _decl_from(attributed) == ("struct", "NavigationStack"),
          repr(_decl_from(attributed)))
    check("attribute-only line is not a declaration",
          _decl_from("@available(iOS 16.0, macOS 13.0, *)") is None)
    check("leading attributes stripped without eating the declaration",
          _strip_leading_attributes("@frozen @propertyWrapper public struct State<Value> {")
          .startswith("public struct State"))

    # Apple's sentinel means "deprecated, version unspecified" — comparing it
    # numerically would classify ~150 live deprecations as far-future.
    av = parse_available('iOS, introduced: 13.0, deprecated: 100000.0, renamed: "foregroundStyle(_:)"')
    check("deprecation sentinel recognised, not compared numerically",
          av is not None and av.deprecated_unspecified and av.deprecated is None,
          repr(av))

    pins = load_pins()
    symbols = []
    for module, path in interface_paths(pins):
        symbols += parse_interface(path, module)
    names = {s.name for s in symbols}

    # Both frameworks must be parsed: foregroundColor lives in SwiftUICore,
    # so parsing only SwiftUI silently loses a chunk of the deprecation set.
    modules = {s.module for s in symbols}
    check("both SwiftUI and SwiftUICore parsed",
          {"SwiftUI", "SwiftUICore"} <= modules, str(modules))

    # Canary symbols. If the parser regresses, these vanish before anything
    # else does, and no test that only counts totals would notice.
    canaries = {"NavigationStack", "NavigationView", "List", "State", "Text",
                "Button", "VStack", "ScrollViewReader", "foregroundColor"}
    missing = canaries - names
    check("canary symbols present", not missing, f"missing {sorted(missing)}")

    deprecated = [s for s in symbols
                  if s.availability.deprecated or s.availability.deprecated_unspecified]
    check("deprecations found", len(deprecated) > 200, f"only {len(deprecated)}")
    check("rename hints extracted",
          sum(1 for s in deprecated if s.availability.renamed) > 50)

    # A floor, not an exact count — the SDK may add symbols, but a sharp drop
    # means the parser broke.
    check("symbol count above floor", len(symbols) > 10000, f"only {len(symbols)}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
