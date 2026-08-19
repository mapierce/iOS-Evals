"""Build one sample against the pinned SDK and capture diagnostics.

Compile flags are assembled from config/pins.toml in exactly one place. Any
divergence between the baseline test and a scoring run would invalidate results,
so nothing else may hand-roll these flags.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from groundtruth.sdk import REPO_ROOT, load_pins, sdk_path

SCAFFOLD = REPO_ROOT / "scaffold"
BEGIN = "// GENERATED-SAMPLE-BEGIN"
END = "// GENERATED-SAMPLE-END"


@dataclass
class BuildResult:
    ok: bool
    stderr: str
    dia_paths: list[Path]
    workdir: Path


def compile_flags(pins: dict, sdk: Path) -> list[str]:
    target = f"{pins['compile']['arch']}{pins['target']['deployment_target']}"
    flags = [
        "-Xswiftc", "-target", "-Xswiftc", target,
        "-Xswiftc", "-sdk", "-Xswiftc", str(sdk),
        # SwiftPM otherwise hands clang the macOS sysroot and the build dies on
        # "cannot load underlying module for 'UIKit'".
        "-Xcc", "-isysroot", "-Xcc", str(sdk),
        "-Xcc", "-target", "-Xcc", target,
    ]
    if pins["compile"].get("warn_soft_deprecated"):
        flags += ["-Xswiftc", "-warn-soft-deprecated"]
    # Structured diagnostics. Never regex the human-readable text.
    flags += ["-Xswiftc", "-serialize-diagnostics"]
    return flags


def build_source(source: str, pins: dict | None = None, keep: bool = False) -> BuildResult:
    """Copy the scaffold to a temp dir, splice `source` in, build it."""
    pins = pins or load_pins()
    sdk = sdk_path(pins)

    workdir = Path(tempfile.mkdtemp(prefix="ios-evals-"))
    pkg = workdir / "Sample"
    shutil.copytree(SCAFFOLD, pkg, ignore=shutil.ignore_patterns(".build"))

    swift = pkg / "Sources" / "Sample" / "Sample.swift"
    text = swift.read_text()
    if BEGIN not in text or END not in text:
        raise RuntimeError(f"scaffold lost its splice markers: {swift}")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    swift.write_text(f"{head}{BEGIN}\n{source.rstrip()}\n{END}{tail}")

    proc = subprocess.run(
        ["swift", "build", *compile_flags(pins, sdk)],
        cwd=pkg, capture_output=True, text=True,
    )
    dias = sorted(pkg.rglob("*.dia"))
    result = BuildResult(
        ok=proc.returncode == 0,
        stderr=proc.stderr + proc.stdout,
        dia_paths=dias,
        workdir=workdir,
    )
    if not keep:
        # Caller owns cleanup when it needs the .dia files.
        pass
    return result
