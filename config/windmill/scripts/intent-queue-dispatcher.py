#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


DEFAULT_REPO_ROOT = Path("/srv/proxmox_florin_server")


def _load_impl(repo_root: Path) -> ModuleType:
    impl_path = repo_root / "scripts" / "intent_queue_dispatcher.py"
    spec = importlib.util.spec_from_file_location("lv3_intent_queue_dispatcher", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load intent queue dispatcher implementation from {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(
    repo_root: str = str(DEFAULT_REPO_ROOT),
    *,
    resource_hints: list[str] | None = None,
    workflow_hints: list[str] | None = None,
    max_items: int = 5,
) -> dict:
    impl = _load_impl(Path(repo_root))
    return impl.main(
        repo_root=repo_root,
        resource_hints=resource_hints or [],
        workflow_hints=workflow_hints or [],
        max_items=max_items,
    )


if __name__ == "__main__":
    impl = _load_impl(DEFAULT_REPO_ROOT)
    args = impl.build_parser().parse_args()
    result = main(
        repo_root=args.repo_root,
        resource_hints=args.resource_hint,
        workflow_hints=args.workflow_hint,
        max_items=args.max_items,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
