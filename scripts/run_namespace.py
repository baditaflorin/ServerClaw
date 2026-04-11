#!/usr/bin/env python3
"""Resolve controller-local run namespaces for mutable execution artifacts."""

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

from platform.run_namespace import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(main())
