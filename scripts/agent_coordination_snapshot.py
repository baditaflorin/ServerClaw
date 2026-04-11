#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from script_bootstrap import ensure_repo_root_on_path

REPO_ROOT = ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime
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
    payload["summary"]["generated_at"] = payload["summary"].get("generated_at") or utcnow().isoformat().replace(
        "+00:00", "Z"
    )

    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{payload['receipt_id']}.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(target)
        _publish_receipt_to_outline(target)
        return 0

    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the current agent coordination map and optionally write a receipt."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true", help="Write the snapshot into receipts/agent-coordination.")
    return parser


def _publish_receipt_to_outline(receipt_path: Path) -> None:
    import os
    import subprocess
    import sys as _sys

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = Path(__file__).resolve().parents[1] / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = Path(__file__).resolve().parent / "outline_tool.py"
    if not outline_tool.exists() or not receipt_path.exists():
        return
    try:
        subprocess.run(
            [_sys.executable, str(outline_tool), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(main(repo_root=args.repo_root, output_dir=args.output_dir, write=args.write))
