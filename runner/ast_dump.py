"""Dump a parsed Swift AST as JSON, without requiring the source to typecheck.

Uses `swiftc -dump-parse -dump-ast-format json`. Parse-only is deliberate: the
functional gate and availability attribution must work on samples that fail to
build, and availability violations are hard compile errors.

The compiler does not guarantee this JSON is stable across toolchain versions.
That is acceptable because the toolchain is pinned, but tests/test_ast.py pins
the node kinds we depend on so a toolchain bump fails loudly instead of silently
returning nothing.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from groundtruth.sdk import load_pins, sdk_path


class ASTDumpError(RuntimeError):
    pass


def dump_ast(source: str, pins: dict | None = None) -> dict:
    """Parse `source` and return the AST as JSON.

    A non-zero exit is expected and ignored: type errors are the normal case
    here. Only a missing or unparseable JSON payload is an error.
    """
    pins = pins or load_pins()
    sdk = sdk_path(pins)
    target = f"{pins['compile']['arch']}{pins['target']['deployment_target']}"

    with tempfile.TemporaryDirectory(prefix="ios-evals-ast-") as tmp:
        src = Path(tmp) / "Sample.swift"
        src.write_text(source)
        proc = subprocess.run(
            [
                "swiftc", "-dump-parse",
                "-dump-ast-format", "json",
                "-target", target,
                "-sdk", str(sdk),
                str(src),
            ],
            capture_output=True, text=True,
        )

    payload = proc.stdout.strip()
    if not payload:
        raise ASTDumpError(
            "swiftc produced no AST JSON; the dump format may have changed.\n"
            + proc.stderr[:2000]
        )
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ASTDumpError(f"AST JSON did not parse: {exc}") from exc
