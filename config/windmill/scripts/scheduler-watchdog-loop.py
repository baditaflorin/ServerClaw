#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0172 scheduler watchdog loop."""

from __future__ import annotations

import os

import importlib.util
import json
from pathlib import Path
from types import ModuleType


DEFAULT_REPO_ROOT = Path(os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))


def _load_impl(repo_root: Path) -> ModuleType:
    impl_path = repo_root / "windmill" / "scheduler" / "watchdog-loop.py"
    spec = importlib.util.spec_from_file_location("lv3_scheduler_watchdog_loop", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load watchdog implementation from {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(repo_path: str = str(DEFAULT_REPO_ROOT)) -> dict:
    impl = _load_impl(Path(repo_path))
    return impl.main(repo_path=repo_path)


if __name__ == "__main__":
    impl = _load_impl(DEFAULT_REPO_ROOT)
    args = impl.build_parser().parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
