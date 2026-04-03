#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from controller_automation_toolkit import emit_cli_error
from platform.workstream_registry import (
    compatibility_matches_source,
    has_sharded_sources,
    load_registry,
    migrate_from_compatibility,
    resolve_paths,
    write_assembled_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the shard-backed workstream registry.")
    parser.add_argument("--repo-root", type=Path, help="Repository root. Defaults to the current repo root.")
    parser.add_argument(
        "--compatibility-path",
        type=Path,
        help="Override the workstreams.yaml compatibility artifact path.",
    )
    parser.add_argument("--write", action="store_true", help="Regenerate workstreams.yaml from the shard source.")
    parser.add_argument("--check", action="store_true", help="Fail when workstreams.yaml is stale versus the shard source.")
    parser.add_argument(
        "--migrate-from",
        type=Path,
        help="Create shard files from an existing compatibility registry.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved registry as JSON. Includes archived workstreams when shards exist.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = resolve_paths(repo_root=args.repo_root, compatibility_path=args.compatibility_path)

    try:
        if args.migrate_from:
            result = migrate_from_compatibility(
                repo_root=paths.repo_root,
                compatibility_path=paths.compatibility_path,
                source_registry_path=args.migrate_from,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.write:
            write_assembled_registry(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path)
            print(paths.compatibility_path.relative_to(paths.repo_root))
            return 0

        if args.check:
            if not has_sharded_sources(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path):
                print("No shard source found; nothing to check.")
                return 0
            if compatibility_matches_source(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path):
                print("workstreams.yaml is current.")
                return 0
            print("workstreams.yaml is stale. Regenerate with: python3 scripts/workstream_registry.py --write")
            return 2

        if args.list:
            print(
                json.dumps(
                    load_registry(
                        repo_root=paths.repo_root,
                        compatibility_path=paths.compatibility_path,
                        include_archive=True,
                    ),
                    indent=2,
                )
            )
            return 0

        parser.print_help()
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("workstream registry", exc)


if __name__ == "__main__":
    raise SystemExit(main())
