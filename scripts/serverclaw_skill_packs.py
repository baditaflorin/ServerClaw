#!/usr/bin/env python3
"""Resolve and validate repo-managed ServerClaw SKILL.md packs."""

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

from platform.use_cases.serverclaw_skills import list_serverclaw_skill_packs, validate_serverclaw_skill_pack_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--workspace-id")
    parser.add_argument("--skill-id")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--no-imported", action="store_true", help="Hide mirrored third-party packs from the JSON output.")
    parser.add_argument(
        "--include-prompt-manifest",
        action="store_true",
        help="Include the compact active-skill prompt manifest in the response.",
    )
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.validate:
        payload = validate_serverclaw_skill_pack_repository(repo_root=args.repo_root)
    else:
        payload = list_serverclaw_skill_packs(
            repo_root=args.repo_root,
            workspace_id=args.workspace_id,
            skill_id=args.skill_id,
            include_imported=not args.no_imported,
            include_prompt_manifest=args.include_prompt_manifest,
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
