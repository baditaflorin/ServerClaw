#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.agent import AgentCoordinationStore

DEFAULT_OUTPUT_DIR = REPO_ROOT / "receipts" / "agent-coordination"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def build_receipt_id(now: datetime) -> str:
    return f"{now.strftime('%Y-%m-%d')}-adr-0161-agent-coordination-snapshot"


def main(*, repo_root: Path, output_dir: Path, write: bool) -> int:
    store = AgentCoordinationStore(repo_root=repo_root)
    payload = store.snapshot()
    payload["receipt_id"] = build_receipt_id(utcnow())
    payload["summary"]["generated_at"] = payload["summary"].get("generated_at") or utcnow().isoformat().replace("+00:00", "Z")

    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{payload['receipt_id']}.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(target)
        return 0

    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read the current agent coordination map and optionally write a receipt.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true", help="Write the snapshot into receipts/agent-coordination.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(main(repo_root=args.repo_root, output_dir=args.output_dir, write=args.write))
