"""Load local secrets from .env without adding a dependency.

Real environment variables always win over the file, so CI and one-off
overrides work without editing anything on disk.

Nothing here ever writes a key back out. Keys are read at run time and must
never reach results/, build/, or any committed file.
"""

from __future__ import annotations

import os
from pathlib import Path

from groundtruth.sdk import REPO_ROOT

ENV_PATH = REPO_ROOT / ".env"


class MissingCredential(RuntimeError):
    pass


def load_env(path: Path = ENV_PATH) -> None:
    """Read KEY=VALUE lines into os.environ, without overwriting what's set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        # Tolerate quoted values; a key is never quoted.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def require(name: str) -> str:
    """Return an environment variable, or fail loudly with how to set it."""
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredential(
            f"{name} is not set.\n"
            f"  cp .env.example .env    then fill in {name}\n"
            f"  or:  export {name}=...\n"
            f"Nothing will run without it — a partial run is worse than a crash."
        )
    return value
