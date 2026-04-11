#!/usr/bin/env python3
"""Cache and recall validation gate results keyed by content hash (ADR 0392 Phase 3.2).

Usage:
    # Check if current tree has a cached passing result:
    python scripts/gate_result_cache.py check --gates schema-validation service-completeness

    # Store a passing result for the current tree:
    python scripts/gate_result_cache.py store --gates schema-validation service-completeness

    # Invalidate cache for current tree:
    python scripts/gate_result_cache.py invalidate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".ansible" / "gate-cache"
DEFAULT_TTL_SECONDS = 3600


def _content_hash() -> str:
    """Compute a hash of all tracked files that gate validation depends on."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    staged = result.stdout.strip()

    result = subprocess.run(
        ["git", "diff", "HEAD", "--stat"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    diff_stat = result.stdout.strip()

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    head_sha = result.stdout.strip()

    composite = f"{head_sha}\n{staged}\n{diff_stat}"
    return hashlib.sha256(composite.encode()).hexdigest()


def _cache_path(content_hash: str) -> Path:
    return CACHE_DIR / f"{content_hash}.json"


def handle_check(args: argparse.Namespace) -> int:
    content_hash = _content_hash()
    cache_file = _cache_path(content_hash)

    if not cache_file.exists():
        print(f"MISS: no cached result for {content_hash[:12]}...")
        return 1

    entry = json.loads(cache_file.read_text(encoding="utf-8"))
    validated_at = entry.get("validated_at", 0)
    ttl = entry.get("ttl_seconds", DEFAULT_TTL_SECONDS)
    age = time.time() - validated_at

    if age > ttl:
        print(f"EXPIRED: cached result for {content_hash[:12]}... is {int(age)}s old (ttl={ttl}s)")
        cache_file.unlink(missing_ok=True)
        return 1

    cached_gates = set(entry.get("gates_passed", []))
    requested_gates = set(args.gates)
    missing = requested_gates - cached_gates
    if missing:
        print(f"PARTIAL: cached result missing gates: {sorted(missing)}")
        return 1

    print(f"HIT: all {len(requested_gates)} gates cached as passing ({int(age)}s ago)")
    return 0


def handle_store(args: argparse.Namespace) -> int:
    content_hash = _content_hash()
    cache_file = _cache_path(content_hash)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    existing_gates: list[str] = []
    if cache_file.exists():
        existing = json.loads(cache_file.read_text(encoding="utf-8"))
        existing_gates = existing.get("gates_passed", [])

    all_gates = sorted(set(existing_gates + args.gates))
    entry = {
        "content_hash": content_hash,
        "gates_passed": all_gates,
        "validated_at": time.time(),
        "ttl_seconds": args.ttl,
    }
    cache_file.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"STORED: {len(all_gates)} gates for {content_hash[:12]}... (ttl={args.ttl}s)")
    return 0


def handle_invalidate(_args: argparse.Namespace) -> int:
    content_hash = _content_hash()
    cache_file = _cache_path(content_hash)
    if cache_file.exists():
        cache_file.unlink()
        print(f"INVALIDATED: {content_hash[:12]}...")
    else:
        print(f"NOOP: no cache entry for {content_hash[:12]}...")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validation gate result cache (ADR 0392)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Check if gates have a cached passing result.")
    check_parser.add_argument("--gates", nargs="+", required=True, help="Gate names to check.")

    store_parser = subparsers.add_parser("store", help="Store a passing gate result.")
    store_parser.add_argument("--gates", nargs="+", required=True, help="Gate names that passed.")
    store_parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS, help="Cache TTL in seconds.")

    subparsers.add_parser("invalidate", help="Invalidate cached result for current tree state.")

    args = parser.parse_args(argv)
    if args.command == "check":
        return handle_check(args)
    if args.command == "store":
        return handle_store(args)
    if args.command == "invalidate":
        return handle_invalidate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
