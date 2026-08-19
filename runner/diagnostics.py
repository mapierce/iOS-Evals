"""Read clang/swift serialized diagnostics (.dia) into structured records.

Diagnostics are consumed from the binary serialized form, never by regex over
human-readable compiler text. The .dia layout is defined by clang's
SerializedDiagnostics.h.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from .bitstream import BitstreamReader

BLOCK_META = 8
BLOCK_DIAG = 9

RECORD_VERSION = 1
RECORD_DIAG = 2
RECORD_SOURCE_RANGE = 3
RECORD_DIAG_FLAG = 4
RECORD_CATEGORY = 5
RECORD_FILENAME = 6
RECORD_FIXIT = 7

# clang SerializedDiagnostics.h Level. NOTE: this is NOT
# DiagnosticsEngine::Level — the serialized enum orders remark last, so reusing
# the in-memory enum silently reports every warning as a remark.
SEVERITY = {1: "note", 2: "warning", 3: "error", 4: "fatal", 5: "remark"}

MAGIC = b"DIAG"


def _group_name(category: str) -> str:
    """Swift writes the category as "DeprecatedDeclaration@<docs url>"."""
    return category.split("@", 1)[0] if category else ""


@dataclass
class Diagnostic:
    severity: str
    filename: str
    line: int
    column: int
    message: str
    group: str         # diagnostic group, e.g. "DeprecatedDeclaration"
    category_raw: str  # Swift encodes this as "Group@https://docs.swift.org/..."
    flag_raw: str

    @property
    def is_error(self) -> bool:
        return self.severity in ("error", "fatal")

    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"


def parse_dia(path: Path) -> list[Diagnostic]:
    data = path.read_bytes()
    if data[:4] != MAGIC:
        raise ValueError(f"not a serialized diagnostics file: {path}")

    reader = BitstreamReader(data[4:])
    files: dict[int, str] = {}
    flags: dict[int, str] = {}
    categories: dict[int, str] = {}
    out: list[Diagnostic] = []

    for block_id, rec in reader.records():
        if rec.code == RECORD_FILENAME:
            # [file_id, size, timestamp, name_len] + blob
            if rec.values:
                files[rec.values[0]] = rec.blob.decode("utf-8", "replace")
        elif rec.code == RECORD_DIAG_FLAG:
            if rec.values:
                flags[rec.values[0]] = rec.blob.decode("utf-8", "replace")
        elif rec.code == RECORD_CATEGORY:
            if rec.values:
                categories[rec.values[0]] = rec.blob.decode("utf-8", "replace")
        elif rec.code == RECORD_DIAG and block_id == BLOCK_DIAG:
            # [severity, file, line, col, offset, category, flag] + blob message
            v = rec.values
            if len(v) < 7:
                continue
            out.append(
                Diagnostic(
                    severity=SEVERITY.get(v[0], f"unknown({v[0]})"),
                    filename=files.get(v[1], ""),
                    line=v[2],
                    column=v[3],
                    message=rec.blob.decode("utf-8", "replace"),
                    group=_group_name(categories.get(v[5], "")),
                    category_raw=categories.get(v[5], ""),
                    flag_raw=flags.get(v[6], ""),
                )
            )

    # Late-arriving name records: .dia interns strings as first seen, so a
    # diagnostic can reference an id defined after it. Resolve in a second pass.
    for d in out:
        if not d.filename:
            d.filename = files.get(0, "")
    return out


def diagnostic_to_dict(d: Diagnostic) -> dict:
    return asdict(d)
