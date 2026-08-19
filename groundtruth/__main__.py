"""Build the ground truth artifact from the pinned SDK on disk.

    python3 -m groundtruth [-o build/groundtruth.json]

Machine-generated every run. Never hand-edited, never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .parse_interface import parse_interface, symbol_to_dict
from .sdk import REPO_ROOT, PINS_PATH, load_pins, interface_paths, xcode_build, sdk_path


def version_tuple(v: str) -> tuple[int, ...]:
    parts = []
    for chunk in v.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(prog="groundtruth")
    ap.add_argument("-o", "--out", type=Path, default=REPO_ROOT / "build" / "groundtruth.json")
    args = ap.parse_args()

    pins = load_pins()
    build = xcode_build(pins)          # raises on mismatch
    root = sdk_path(pins)              # raises on mismatch
    target = pins["target"]["deployment_target"]
    tv = version_tuple(target)

    symbols, sources = [], []
    for module, path in interface_paths(pins):
        symbols += parse_interface(path, module)
        sources.append(
            {"module": module, "path": str(path), "sha256": sha256(path)}
        )

    # Facts only. The target-relative counts below are a summary for humans;
    # scoring re-derives its own classification from the raw records.
    deprecated = [
        s for s in symbols
        if s.availability.deprecated or s.availability.deprecated_unspecified
    ]
    above_target = [
        s for s in symbols
        if s.availability.introduced and version_tuple(s.availability.introduced) > tv
    ]

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pins": {
            "sha256": sha256(PINS_PATH),
            "xcode_build": build,
            "sdk_version": pins["sdk"]["sdk_version"],
            "sdk_path": str(root),
            "deployment_target": target,
        },
        "sources": sources,
        "counts": {
            "symbols": len(symbols),
            "deprecated": len(deprecated),
            "introduced_above_target": len(above_target),
        },
        "symbols": [symbol_to_dict(s) for s in symbols],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=1))

    print(f"SDK          {root}")
    print(f"Xcode build  {build}")
    print(f"target       iOS {target}")
    for src in sources:
        print(f"  parsed     {src['module']:12} {src['sha256'][:12]}")
    print(f"symbols      {len(symbols)}")
    print(f"  deprecated {len(deprecated)}")
    print(f"  above tgt  {len(above_target)}")
    print(f"wrote        {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
