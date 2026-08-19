"""AST extraction.

The parse-only AST JSON is explicitly NOT guaranteed stable across toolchain
versions. These checks pin the node kinds and shapes the gate depends on, so a
toolchain bump fails loudly instead of silently returning zero references and
scoring every model as perfectly current.

    python3 tests/test_ast.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.ast_dump import dump_ast
from scoring.references import extract_references, declared_names

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        if detail:
            print(f"        {detail}")
        FAILURES.append(name)


SAMPLE = '''import SwiftUI
struct MyCard: View {
    let title: String
    func helper() -> Int { 1 }
    var body: some View {
        NavigationView {
            Text(title)
                .foregroundColor(.blue)
                .foregroundColor(.red)
                .presentationSizing(.form)
        }
    }
}'''


def main() -> int:
    print("AST extraction\n")

    ast = dump_ast(SAMPLE)
    names = [r.name for r in extract_references(ast)]
    kinds = {r.node_kind for r in extract_references(ast)}

    check("dump produces a source_file root", ast.get("_kind") == "source_file")

    # Node kinds the gate reads. If the dump format renames these, every
    # AST-derived metric silently reads zero.
    check("unresolved_decl_ref_expr present (type refs)",
          "unresolved_decl_ref_expr" in kinds, str(kinds))
    check("unresolved_dot_expr present (modifier calls)",
          "unresolved_dot_expr" in kinds, str(kinds))

    check("type reference captured", "NavigationView" in names, str(names))
    check("modifier call captured", "foregroundColor" in names, str(names))
    check("above-target modifier captured", "presentationSizing" in names, str(names))

    # Declarations nest their name as name.base_name.name. A naive
    # node.get("name") returns nothing and every model-declared symbol leaks
    # through as an external reference.
    decls = declared_names(ast)
    check("declaration names resolved through base_name",
          {"MyCard", "title", "helper", "body"} <= decls, str(sorted(decls)))
    leaked = {"MyCard", "title", "helper", "body"} & set(names)
    check("model's own declarations excluded from references",
          not leaked, f"leaked {leaked}")

    check("repeat call sites counted per occurrence",
          names.count("foregroundColor") == 2, str(names))

    # The whole point of parse-only: this must work on code that cannot build.
    broken = dump_ast('''import SwiftUI
struct B: View {
    var body: some View { Text("x").presentationSizing(.form) }
}''')
    bnames = [r.name for r in extract_references(broken)]
    check("references recovered from source that does not typecheck",
          "presentationSizing" in bnames, str(bnames))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
