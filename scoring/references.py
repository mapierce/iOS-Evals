"""Extract symbol references from a parsed Swift AST.

Turns the AST JSON from runner.ast_dump into counted call sites. Works on
source that does not typecheck, so it is valid for every sample regardless of
whether the sample built.

Name-based, not resolution-based: the parse-only AST gives call-site names, not
resolved declarations. Overload sets sharing a base name collapse together. This
limitation is recorded in docs/metrics.md.
"""

from __future__ import annotations

from dataclasses import dataclass

# Node kinds that carry a reference to something the sample did not declare.
# Pinned by tests/test_ast.py — the dump format is not guaranteed stable across
# toolchains, and a silent rename here would zero every AST-derived metric.
REF_KINDS = {
    "unresolved_decl_ref_expr": "name",    # type refs: NavigationView, Text
    "unresolved_dot_expr": "field",        # modifiers: .foregroundColor(...)
    "unresolved_member_expr": "name",      # leading-dot members: .blue, .form
    "type_ident": "name",                  # explicit type annotations
}

# Node kinds that introduce a name the sample owns. Excluded from references so
# a model's own helper named `body` is never scored as a SwiftUI symbol.
DECL_KINDS = {
    "struct_decl", "class_decl", "enum_decl", "protocol_decl", "actor_decl",
    "func_decl", "var_decl", "param_decl", "typealias_decl", "enum_element_decl",
    "accessor_decl", "subscript_decl", "pattern_binding_decl",
}


@dataclass(frozen=True)
class Reference:
    name: str
    node_kind: str
    offset: int


def _node_offset(node: dict) -> int:
    rng = node.get("range")
    if isinstance(rng, dict) and isinstance(rng.get("start"), int):
        return rng["start"]
    return -1


def _decl_name(node: dict) -> str | None:
    """Pull a declaration's name out of the AST.

    Declarations nest it as node["name"]["base_name"]["name"] rather than
    carrying it inline, so a naive node.get("name") returns nothing and every
    model-declared symbol leaks through as an external reference.
    """
    name = node.get("name")
    if isinstance(name, str):
        return name
    if isinstance(name, dict):
        base = name.get("base_name")
        if isinstance(base, dict) and isinstance(base.get("name"), str):
            return base["name"]
        if isinstance(name.get("name"), str):
            return name["name"]
    return None


def declared_names(ast: dict) -> set[str]:
    """Names the sample declares itself.

    Excluded from references so a model's own helper named `body` or a property
    named `title` is never counted as a SwiftUI symbol.
    """
    out: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("_kind") in DECL_KINDS:
                found = _decl_name(n)
                if found:
                    out.add(found)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(ast)
    return out


def extract_references(ast: dict, exclude_declared: bool = True) -> list[Reference]:
    """Every reference site in the AST, in source order.

    One entry per occurrence: using a symbol three times yields three
    references, matching how docs/metrics.md counts call sites.
    """
    own = declared_names(ast) if exclude_declared else set()
    refs: list[Reference] = []

    def walk(n):
        if isinstance(n, dict):
            kind = n.get("_kind", "")
            key = REF_KINDS.get(kind)
            if key:
                name = n.get(key)
                if isinstance(name, str) and name and name not in own:
                    refs.append(Reference(name, kind, _node_offset(n)))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(ast)
    refs.sort(key=lambda r: (r.offset if r.offset >= 0 else 1 << 30))
    return refs
