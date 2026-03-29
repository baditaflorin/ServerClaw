#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path


def resolve_repo_root(script_path: Path | None = None) -> Path:
    candidate = (script_path or Path(__file__)).resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "platform" / "__init__.py").exists():
            return parent
    raise RuntimeError(f"Unable to resolve repository root from {candidate}")


REPO_ROOT = resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.scheduler import HttpWindmillClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Windmill script and wait for its result.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get("WINDMILL_TOKEN", "").strip()
    if not token:
        print("WINDMILL_TOKEN is required", file=sys.stderr)
        return 2

    payload = json.loads(args.payload_json)
    client = HttpWindmillClient(
        base_url=args.base_url,
        token=token,
        workspace=args.workspace,
        request_timeout_seconds=args.timeout,
    )
    try:
        result = client.run_workflow_wait_result(
            args.path,
            payload,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode("utf-8"))
        return 1
    except (RuntimeError, TimeoutError, urllib.error.URLError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    if result is None:
        return 0
    if isinstance(result, str):
        sys.stdout.write(result)
    else:
        sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
