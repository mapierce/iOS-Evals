"""Parse @available attributes out of SDK .swiftinterface files.

Emits facts only. No policy: this module never decides what counts as a
violation, because that depends on the deployment target and belongs to
scoring. Ground truth is always derived from the SDK on disk, never
hand-maintained.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Apple's sentinel for "deprecated, but no version was specified". It means
# deprecated *now*, not deprecated in the year 100000. ~800 SwiftUI symbols use
# it, including NavigationView and foregroundColor, so mishandling it would
# silently drop most of the deprecation signal.
DEPRECATED_UNSPECIFIED = "100000.0"

PLATFORM = "iOS"

_AVAILABLE_RE = re.compile(r"@available\s*\(")
_SHORT_TOKEN_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)\s+([0-9]+(?:\.[0-9]+)*)$")
_KV_RE = re.compile(r"^([A-Za-z]+)\s*:\s*(.*)$")

# Declaration forms that carry availability in a .swiftinterface.
_DECL_RE = re.compile(
    r"\b(?P<kind>struct|class|enum|protocol|actor|typealias|func|var|let|init|case|subscript|associatedtype)\b"
    r"(?:\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*))?"
)
_EXTENSION_RE = re.compile(r"\bextension\s+(?P<name>[A-Za-z_][A-Za-z0-9_.]*)")
_OPERATOR_FUNC_RE = re.compile(r"\bfunc\s+([^\s(<]+)\s*[(<]")


@dataclass
class Availability:
    """One platform's availability facts for one symbol."""

    introduced: str | None = None
    deprecated: str | None = None
    deprecated_unspecified: bool = False
    obsoleted: str | None = None
    unavailable: bool = False
    renamed: str | None = None
    message: str | None = None


@dataclass
class Symbol:
    name: str
    kind: str
    module: str
    context: str | None = None          # enclosing type / extension, if any
    line: int = 0
    availability: Availability = field(default_factory=Availability)

    @property
    def qualified(self) -> str:
        return f"{self.context}.{self.name}" if self.context else self.name


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not nested in parens/brackets/strings."""
    parts, buf, depth, in_str, esc = [], [], 0, False, False
    for ch in text:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\" and in_str:
            buf.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            buf.append(ch)
            continue
        if not in_str:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    return v


def parse_available(inner: str, platform: str = PLATFORM) -> Availability | None:
    """Parse the inside of one @available(...) for a single platform.

    Returns None when the attribute does not apply to `platform`.

    Handles the four shapes that appear in practice:
        @available(iOS 26.0, *)                              -> introduced
        @available(iOS, introduced: 13.0, deprecated: 1e5)   -> long form
        @available(*, deprecated, renamed: "x")              -> all platforms
        @available(iOS, unavailable)                         -> unavailable
    """
    tokens = _split_top_level(inner)
    if not tokens:
        return None

    head = tokens[0].strip()

    # Short form: every token is either "Platform X.Y" or "*".
    if _SHORT_TOKEN_RE.match(head):
        for tok in tokens:
            m = _SHORT_TOKEN_RE.match(tok.strip())
            if m and m.group(1) == platform:
                return Availability(introduced=m.group(2))
        return None

    # Long form / wildcard form: head names the platform (or "*" for all).
    if head != platform and head != "*":
        return None

    av = Availability()
    for tok in tokens[1:]:
        tok = tok.strip()
        kv = _KV_RE.match(tok)
        if kv:
            key, raw = kv.group(1), _unquote(kv.group(2))
            if key == "introduced":
                av.introduced = raw
            elif key == "deprecated":
                if raw == DEPRECATED_UNSPECIFIED:
                    av.deprecated_unspecified = True
                else:
                    av.deprecated = raw
            elif key == "obsoleted":
                av.obsoleted = raw
            elif key == "renamed":
                av.renamed = raw
            elif key == "message":
                av.message = raw
        elif tok == "deprecated":
            av.deprecated_unspecified = True
        elif tok == "unavailable":
            av.unavailable = True
    return av


def _merge(base: Availability, extra: Availability) -> Availability:
    """Later attributes fill gaps; a set field is never overwritten by None."""
    return Availability(
        introduced=extra.introduced or base.introduced,
        deprecated=extra.deprecated or base.deprecated,
        deprecated_unspecified=base.deprecated_unspecified or extra.deprecated_unspecified,
        obsoleted=extra.obsoleted or base.obsoleted,
        unavailable=base.unavailable or extra.unavailable,
        renamed=extra.renamed or base.renamed,
        message=extra.message or base.message,
    )


def _extract_attr_bodies(line: str) -> list[str]:
    """Return the inner text of each @available(...) on a line, paren-balanced."""
    bodies = []
    for m in _AVAILABLE_RE.finditer(line):
        i = m.end()  # just past the opening paren
        depth, in_str, esc, start = 1, False, False, i
        while i < len(line) and depth:
            ch = line[i]
            if esc:
                esc = False
            elif ch == "\\" and in_str:
                esc = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        if depth == 0:
            bodies.append(line[start : i - 1])
    return bodies


def _strip_leading_attributes(text: str) -> str:
    """Drop leading @attributes from a declaration line.

    Most SwiftUI views declare as `@_Concurrency.MainActor @preconcurrency
    public struct Foo`, so treating any line starting with "@" as
    attribute-only silently discards the declaration itself.
    """
    s = text.strip()
    while s.startswith("@"):
        i = 1
        while i < len(s) and (s[i].isalnum() or s[i] in "_."):
            i += 1
        if i < len(s) and s[i] == "(":           # attribute with arguments
            depth = 0
            while i < len(s):
                if s[i] == "(":
                    depth += 1
                elif s[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        nxt = s[i:].lstrip()
        if nxt == s:                              # no progress; avoid a spin
            break
        s = nxt
    return s


def _decl_from(line: str) -> tuple[str, str] | None:
    """Return (kind, name) for a declaration line, or None."""
    stripped = _strip_leading_attributes(line)
    if not stripped or stripped.startswith("//") or stripped.startswith("#"):
        return None

    ext = _EXTENSION_RE.search(stripped)
    if ext:
        return ("extension", ext.group("name"))

    m = _DECL_RE.search(stripped)
    if not m:
        return None
    kind, name = m.group("kind"), m.group("name")
    if kind == "func" and not name:
        op = _OPERATOR_FUNC_RE.search(stripped)
        if op:
            name = op.group(1)
    if kind == "init":
        name = "init"
    if not name:
        return None
    return (kind, name)


def parse_interface(path: Path, module: str, platform: str = PLATFORM) -> list[Symbol]:
    """Walk one .swiftinterface, attaching pending @available to the next decl."""
    symbols: list[Symbol] = []
    pending: Availability | None = None
    pending_any = False
    # (name, brace depth at entry, availability inherited by members)
    context_stack: list[tuple[str, int, Availability | None]] = []
    depth = 0

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("//")[0] if raw.lstrip().startswith("//") else raw
        bodies = _extract_attr_bodies(line)

        if bodies:
            for body in bodies:
                av = parse_available(body, platform)
                if av is not None:
                    pending = av if pending is None else _merge(pending, av)
                    pending_any = True
            # Attribute-only line: keep accumulating.
            if line.strip().startswith("@") and not _decl_from(line):
                depth += line.count("{") - line.count("}")
                continue

        decl = _decl_from(line)
        if decl:
            kind, name = decl
            context = context_stack[-1][0] if context_stack else None
            # An @available on an extension or type applies to every member
            # inside it. Members inherit it, and their own attributes win on
            # any field they set.
            inherited = context_stack[-1][2] if context_stack else None
            own = pending if pending_any else None

            if kind != "extension":
                effective = own
                if inherited is not None:
                    effective = inherited if own is None else _merge(inherited, own)
                if effective is not None:
                    symbols.append(
                        Symbol(
                            name=name,
                            kind=kind,
                            module=module,
                            context=context,
                            line=lineno,
                            availability=effective,
                        )
                    )

            if kind in ("extension", "struct", "class", "enum", "protocol", "actor"):
                if "{" in line:
                    scope_av = own
                    if inherited is not None:
                        scope_av = inherited if own is None else _merge(inherited, own)
                    context_stack.append((name, depth, scope_av))
            pending, pending_any = None, False

        opens, closes = line.count("{"), line.count("}")
        depth += opens - closes
        while context_stack and depth <= context_stack[-1][1]:
            context_stack.pop()

    return symbols


def symbol_to_dict(s: Symbol) -> dict:
    d = asdict(s)
    d["qualified"] = s.qualified
    return d
