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

from platform.policy.toolchain import ensure_policy_toolchain


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure the ADR 0230 OPA/Conftest toolchain is available.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root that owns the policy cache.")
    parser.add_argument("--install-root", type=Path, help="Optional explicit install root for the managed tool cache.")
    parser.add_argument("--json", action="store_true", help="Print the resolved toolchain as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    toolchain = ensure_policy_toolchain(repo_root=args.repo_root.resolve(), install_root=args.install_root)
    payload = {
        "install_root": str(toolchain.install_root),
        "opa": {"version": toolchain.opa.version, "path": str(toolchain.opa.path)},
        "conftest": {"version": toolchain.conftest.version, "path": str(toolchain.conftest.path)},
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"OPA {toolchain.opa.version}: {toolchain.opa.path}")
    print(f"Conftest {toolchain.conftest.version}: {toolchain.conftest.path}")
    print(f"Install root: {toolchain.install_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
