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
from platform.ansible import execute_dependency_wave_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute dependency-wave manifests for parallel live apply.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Optional playbook metadata catalog. Defaults to config/dependency-wave-playbooks.yaml under --repo-root.",
    )
    parser.add_argument("--env", default="production")
    parser.add_argument(
        "--extra-args", default="", help="Literal EXTRA_ARGS passed through to the underlying make targets."
    )
    parser.add_argument("--lock-ttl-seconds", type=int, default=1800)
    parser.add_argument("--heartbeat-seconds", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    catalog_path = args.catalog if args.catalog is not None else repo_root / "config" / "dependency-wave-playbooks.yaml"
    if not catalog_path.is_absolute():
        catalog_path = repo_root / catalog_path

    try:
        result = execute_dependency_wave_manifest(
            repo_root=repo_root,
            manifest_path=manifest_path,
            catalog_path=catalog_path,
            env=args.env,
            extra_args=args.extra_args,
            lock_ttl_seconds=args.lock_ttl_seconds,
            heartbeat_seconds=args.heartbeat_seconds,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return emit_cli_error("dependency wave apply", exc)

    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"completed", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
