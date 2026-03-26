#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error, repo_path
from platform.config_merge import ConfigMergeRegistry, DuplicateKeyError, validate_merge_eligible_catalog


DEFAULT_DSN_ENV_VARS = ("LV3_CONFIG_MERGE_DSN", "DATABASE_URL")


def default_dsn() -> str:
    for key in DEFAULT_DSN_ENV_VARS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _load_entry_payload(raw: str) -> dict:
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def build_registry(repo_root: Path, dsn: str | None, publish_nats: bool = False) -> ConfigMergeRegistry:
    resolved_dsn = (dsn or default_dsn()).strip()
    if not resolved_dsn:
        raise RuntimeError("set LV3_CONFIG_MERGE_DSN or DATABASE_URL, or pass --dsn")
    return ConfigMergeRegistry(repo_root=repo_root, dsn=resolved_dsn, publish_nats=publish_nats)


def cmd_validate(args: argparse.Namespace) -> int:
    validate_merge_eligible_catalog(args.catalog)
    print(f"Merge-eligible catalog OK: {args.catalog}")
    return 0


def cmd_ensure_schema(args: argparse.Namespace) -> int:
    registry = build_registry(Path(args.repo_root), args.dsn)
    registry.ensure_schema()
    print("Config-merge schema OK")
    return 0


def cmd_stage_append(args: argparse.Namespace) -> int:
    registry = build_registry(Path(args.repo_root), args.dsn)
    entry = _load_entry_payload(args.entry)
    change = registry.stage_append(
        file_path=args.file,
        entry=entry,
        actor=args.actor,
        context_id=args.context_id,
        key_value=args.key_value,
    )
    print(json.dumps(change, indent=2))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    registry = build_registry(Path(args.repo_root), args.dsn)
    payload = registry.read_file(args.file, include_pending=not args.exclude_pending)
    print(json.dumps(payload, indent=2))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    registry = build_registry(Path(args.repo_root), args.dsn, publish_nats=args.publish_nats)
    report = registry.merge_pending(
        file_path=args.file,
        actor=args.actor,
        commit_changes=args.commit,
        push=args.push,
    )
    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage and merge ADR 0158 merge-eligible config changes.")
    parser.add_argument("--repo-root", default=str(repo_path()), help="Repository root to operate on.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate config/merge-eligible-files.yaml.")
    validate.add_argument("--catalog", default=str(repo_path("config", "merge-eligible-files.yaml")))
    validate.set_defaults(func=cmd_validate)

    ensure_schema = subparsers.add_parser("ensure-schema", help="Create the config-merge staging table.")
    ensure_schema.add_argument("--dsn", default=None)
    ensure_schema.set_defaults(func=cmd_ensure_schema)

    stage_append = subparsers.add_parser("stage-append", help="Stage one append operation.")
    stage_append.add_argument("--dsn", default=None)
    stage_append.add_argument("--file", required=True)
    stage_append.add_argument("--entry", required=True, help="JSON payload or @path/to/file.json.")
    stage_append.add_argument("--actor", required=True)
    stage_append.add_argument("--context-id", required=True)
    stage_append.add_argument("--key-value")
    stage_append.set_defaults(func=cmd_stage_append)

    read = subparsers.add_parser("read", help="Render a merge-eligible file with pending changes overlaid.")
    read.add_argument("--dsn", default=None)
    read.add_argument("--file", required=True)
    read.add_argument("--exclude-pending", action="store_true")
    read.set_defaults(func=cmd_read)

    merge = subparsers.add_parser("merge", help="Apply pending staged changes into the repo files.")
    merge.add_argument("--dsn", default=None)
    merge.add_argument("--file")
    merge.add_argument("--actor", default="agent/config-merge-job")
    merge.add_argument("--commit", action="store_true")
    merge.add_argument("--push", action="store_true")
    merge.add_argument("--publish-nats", action="store_true")
    merge.set_defaults(func=cmd_merge)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DuplicateKeyError, FileNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Config merge protocol", exc)


if __name__ == "__main__":
    sys.exit(main())
