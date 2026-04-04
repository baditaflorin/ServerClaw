#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.repo import local_overlay_root


LEGACY_BOOTSTRAP_KEY_NAME = "hetzner_llm_agents_ed25519"
CANONICAL_BOOTSTRAP_KEY_NAME = "bootstrap.id_ed25519"


@dataclass(frozen=True)
class AliasStatus:
    alias_path: str
    legacy_path: str
    status: str


def _create_relative_symlink(alias_path: Path, target_path: Path) -> None:
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    relative_target = Path(target_path.relative_to(alias_path.parent))
    alias_path.symlink_to(relative_target)


def ensure_bootstrap_key_aliases(repo_root: Path) -> list[AliasStatus]:
    ssh_dir = local_overlay_root(repo_root) / "ssh"
    results: list[AliasStatus] = []

    for suffix in ("", ".pub"):
        alias_path = ssh_dir / f"{CANONICAL_BOOTSTRAP_KEY_NAME}{suffix}"
        legacy_path = ssh_dir / f"{LEGACY_BOOTSTRAP_KEY_NAME}{suffix}"

        if alias_path.exists() or alias_path.is_symlink():
            results.append(
                AliasStatus(
                    alias_path=str(alias_path),
                    legacy_path=str(legacy_path),
                    status="present",
                )
            )
            continue

        if not legacy_path.exists():
            results.append(
                AliasStatus(
                    alias_path=str(alias_path),
                    legacy_path=str(legacy_path),
                    status="missing_legacy_source",
                )
            )
            continue

        _create_relative_symlink(alias_path, legacy_path)
        results.append(
            AliasStatus(
                alias_path=str(alias_path),
                legacy_path=str(legacy_path),
                status="materialized",
            )
        )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize the generic shared-overlay bootstrap SSH key aliases from the legacy key names."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repo root whose shared .local overlay should receive the aliases.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = ensure_bootstrap_key_aliases(Path(args.repo_root).resolve())

    if args.json:
        print(json.dumps([asdict(item) for item in results], indent=2))
    else:
        for item in results:
            print(f"{item.status}: {item.alias_path} <= {item.legacy_path}")

    return 0 if all(item.status in {"present", "materialized"} for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
