#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_REPO_PATH = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")


def _load_deadlock_detector_dependencies(repo_root: Path):
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    from platform.coordination import AgentCoordinationMap
    from platform.intent_queue import IntentQueue
    from platform.ledger import LedgerWriter
    from platform.locking import DeadlockDetector, ResourceLockRegistry

    return AgentCoordinationMap, IntentQueue, LedgerWriter, DeadlockDetector, ResourceLockRegistry


def main(
    *,
    repo_path: str = DEFAULT_REPO_PATH,
    lock_registry_path: str | None = None,
    coordination_map_path: str | None = None,
    intent_queue_path: str | None = None,
    ledger_file_path: str | None = None,
) -> dict:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    if lock_registry_path:
        os.environ["LV3_LOCK_REGISTRY_PATH"] = lock_registry_path
    if coordination_map_path:
        os.environ["LV3_COORDINATION_MAP_PATH"] = coordination_map_path
    if intent_queue_path:
        os.environ["LV3_INTENT_QUEUE_PATH"] = intent_queue_path
    if ledger_file_path:
        os.environ["LV3_LEDGER_FILE"] = ledger_file_path

    AgentCoordinationMap, IntentQueue, LedgerWriter, DeadlockDetector, ResourceLockRegistry = (
        _load_deadlock_detector_dependencies(repo_root)
    )

    ledger_writer = None
    if (
        ledger_file_path
        or os.environ.get("LV3_LEDGER_FILE", "").strip()
        or os.environ.get("LV3_LEDGER_DSN", "").strip()
    ):
        ledger_writer = LedgerWriter(nats_publisher=None)

    detector = DeadlockDetector(
        lock_registry=ResourceLockRegistry(),
        coordination_map=AgentCoordinationMap(),
        intent_queue=IntentQueue(),
        ledger_writer=ledger_writer,
    )
    return detector.run_once()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one ADR 0162 deadlock detector pass.")
    parser.add_argument("--repo-path", default=DEFAULT_REPO_PATH)
    parser.add_argument("--lock-registry-path")
    parser.add_argument("--coordination-map-path")
    parser.add_argument("--intent-queue-path")
    parser.add_argument("--ledger-file-path")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                lock_registry_path=args.lock_registry_path,
                coordination_map_path=args.coordination_map_path,
                intent_queue_path=args.intent_queue_path,
                ledger_file_path=args.ledger_file_path,
            ),
            sort_keys=True,
        )
    )
