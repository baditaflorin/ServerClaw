#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_path(script_file: str) -> Path:
    repo_root = Path(script_file).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]
    return repo_root
