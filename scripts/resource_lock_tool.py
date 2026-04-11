#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error
from platform.locking import LockType, ResourceLockRegistry


def build_registry(*, repo_root: Path, state_path: Path | None = None) -> ResourceLockRegistry:
    return ResourceLockRegistry(repo_root=repo_root, state_path=state_path)


def ensure_state_action(*, repo_root: Path, state_path: Path | None = None) -> dict[str, object]:
    registry = build_registry(repo_root=repo_root, state_path=state_path)
    registry.read_all()
    return {
        "status": "ready",
        "state_path": str(registry.state_path),
    }


def list_action(*, repo_root: Path, state_path: Path | None = None) -> dict[str, object]:
    registry = build_registry(repo_root=repo_root, state_path=state_path)
    locks = registry.read_all()
    return {
        "count": len(locks),
        "locks": [entry.as_dict() for entry in locks],
        "state_path": str(registry.state_path),
    }


def acquire_action(
    *,
    repo_root: Path,
    resource: str,
    holder: str,
    lock_type: str,
    ttl_seconds: int,
    wait_seconds: int,
    context_id: str | None,
    metadata: dict[str, object] | None = None,
    state_path: Path | None = None,
) -> dict[str, object]:
    registry = build_registry(repo_root=repo_root, state_path=state_path)
    entry = registry.acquire(
        resource_path=resource,
        lock_type=LockType(lock_type),
        holder=holder,
        context_id=context_id,
        ttl_seconds=ttl_seconds,
        wait_seconds=wait_seconds,
        metadata=metadata,
    )
    return {
        "status": "acquired",
        "lock": entry.as_dict(),
        "state_path": str(registry.state_path),
    }


def release_action(
    *,
    repo_root: Path,
    lock_id: str | None = None,
    resource: str | None = None,
    holder: str | None = None,
    state_path: Path | None = None,
) -> dict[str, object]:
    registry = build_registry(repo_root=repo_root, state_path=state_path)
    released = registry.release(lock_id=lock_id, resource_path=resource, holder=holder)
    return {
        "status": "released",
        "released": released,
        "state_path": str(registry.state_path),
    }


def heartbeat_action(
    *,
    repo_root: Path,
    lock_id: str,
    ttl_seconds: int,
    state_path: Path | None = None,
) -> dict[str, object]:
    registry = build_registry(repo_root=repo_root, state_path=state_path)
    entry = registry.heartbeat(lock_id, ttl_seconds=ttl_seconds)
    return {
        "status": "refreshed" if entry is not None else "missing",
        "lock": entry.as_dict() if entry is not None else None,
        "state_path": str(registry.state_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the ADR 0153 resource lock registry.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--state-path", type=Path, help="Optional explicit path to the lock registry state file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ensure-state", help="Create or validate access to the shared lock-registry state file.")
    subparsers.add_parser("list", help="List active locks.")

    acquire_parser = subparsers.add_parser("acquire", help="Acquire one lock.")
    acquire_parser.add_argument("--resource", required=True)
    acquire_parser.add_argument("--holder", required=True)
    acquire_parser.add_argument("--lock-type", choices=[item.value for item in LockType], required=True)
    acquire_parser.add_argument("--ttl-seconds", type=int, default=300)
    acquire_parser.add_argument("--wait-seconds", type=int, default=0)
    acquire_parser.add_argument("--context-id")
    acquire_parser.add_argument(
        "--metadata-json",
        help="Optional JSON object merged into the lock metadata.",
    )

    release_parser = subparsers.add_parser("release", help="Release one or more locks by id and/or filters.")
    release_parser.add_argument("--lock-id")
    release_parser.add_argument("--resource")
    release_parser.add_argument("--holder")

    heartbeat_parser = subparsers.add_parser("heartbeat", help="Refresh one lock TTL.")
    heartbeat_parser.add_argument("--lock-id", required=True)
    heartbeat_parser.add_argument("--ttl-seconds", type=int, default=300)

    return parser


def parse_metadata(raw: str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--metadata-json must decode to an object")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.command == "ensure-state":
            result = ensure_state_action(repo_root=args.repo_root, state_path=args.state_path)
        elif args.command == "list":
            result = list_action(repo_root=args.repo_root, state_path=args.state_path)
        elif args.command == "acquire":
            result = acquire_action(
                repo_root=args.repo_root,
                resource=args.resource,
                holder=args.holder,
                lock_type=args.lock_type,
                ttl_seconds=args.ttl_seconds,
                wait_seconds=args.wait_seconds,
                context_id=args.context_id,
                metadata=parse_metadata(args.metadata_json),
                state_path=args.state_path,
            )
        elif args.command == "release":
            if not any((args.lock_id, args.resource, args.holder)):
                raise ValueError("release requires at least one of --lock-id, --resource, or --holder")
            result = release_action(
                repo_root=args.repo_root,
                lock_id=args.lock_id,
                resource=args.resource,
                holder=args.holder,
                state_path=args.state_path,
            )
        else:
            result = heartbeat_action(
                repo_root=args.repo_root,
                lock_id=args.lock_id,
                ttl_seconds=args.ttl_seconds,
                state_path=args.state_path,
            )
    except Exception as exc:
        return emit_cli_error("Resource lock registry", exc)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
