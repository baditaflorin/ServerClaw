#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

loaded_platform = sys.modules.get("platform")
if loaded_platform is not None and not hasattr(loaded_platform, "__path__"):
    loaded_platform_file = getattr(loaded_platform, "__file__", "")
    if not str(loaded_platform_file).startswith(str(REPO_ROOT / "platform")):
        sys.modules.pop("platform", None)

from platform.repo import *  # noqa: F401,F403


def resolve_repo_local_path(path_value: str | Path, *, repo_root: Path = REPO_ROOT) -> Path:
    path = Path(path_value).expanduser()
    if path.exists():
        return path
    marker = ".local"
    if marker not in path.parts:
        return path
    marker_index = path.parts.index(marker)
    candidate = repo_root.joinpath(*path.parts[marker_index:])
    return candidate if candidate.exists() else path
