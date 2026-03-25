#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0172 scheduler watchdog loop."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_impl(repo_root: Path) -> ModuleType:
    impl_path = repo_root / "windmill" / "scheduler" / "watchdog-loop.py"
    spec = importlib.util.spec_from_file_location("lv3_scheduler_watchdog_loop", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load watchdog implementation from {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    impl = _load_impl(repo_root)
    args = impl.build_parser().parse_args()
    print(json.dumps(impl.main(repo_path=args.repo_path), indent=2, sort_keys=True))
