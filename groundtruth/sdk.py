"""Locate the pinned SDK on disk and assert it matches config/pins.toml.

Fails loudly. A silent fallback to whatever SDK happens to be installed would
invalidate every score without anyone noticing.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PINS_PATH = REPO_ROOT / "config" / "pins.toml"


class PinMismatch(RuntimeError):
    pass


def load_pins(path: Path = PINS_PATH) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _xcrun(*args: str) -> str:
    return subprocess.check_output(["xcrun", *args], text=True).strip()


def sdk_path(pins: dict) -> Path:
    platform = pins["sdk"]["platform"]
    want = pins["sdk"]["sdk_version"]
    have = _xcrun("--sdk", platform, "--show-sdk-version")
    if have != want:
        raise PinMismatch(
            f"pins.toml requires {platform} SDK {want}, but xcrun reports {have}. "
            f"Install the matching Xcode or update config/pins.toml — do not proceed."
        )
    return Path(_xcrun("--sdk", platform, "--show-sdk-path"))


def xcode_build(pins: dict) -> str:
    out = subprocess.check_output(["xcodebuild", "-version"], text=True)
    build = out.strip().splitlines()[-1].split()[-1]
    want = pins["toolchain"]["xcode_build"]
    if build != want:
        raise PinMismatch(
            f"pins.toml requires Xcode build {want}, but this machine has {build}. "
            f"The compiler is the scorer; a different compiler is a different benchmark."
        )
    return build


def interface_paths(pins: dict) -> list[tuple[str, Path]]:
    """Return (module, .swiftinterface path) for every pinned module."""
    root = sdk_path(pins)
    arch = pins["sdk"]["interface_arch"]
    out = []
    for module in pins["sdk"]["modules"]:
        p = (
            root
            / "System/Library/Frameworks"
            / f"{module}.framework/Modules/{module}.swiftmodule"
            / f"{arch}.swiftinterface"
        )
        if not p.is_file():
            raise FileNotFoundError(f"missing interface for {module}: {p}")
        out.append((module, p))
    return out
