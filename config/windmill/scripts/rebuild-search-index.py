#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from search_fabric import SearchIndexer  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild the LV3 local search index.")
    parser.add_argument("--repo-path", default=str(REPO_ROOT), help="Repository root to index.")
    parser.add_argument("--index-path", default="", help="Optional output path for the generated search index.")
    parser.add_argument(
        "--collection",
        action="append",
        dest="collections",
        help="Limit the rebuild to one or more collections. Repeat for multiple values.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_path).resolve()
    index_path = Path(args.index_path).resolve() if args.index_path else None
    indexer = SearchIndexer(repo_root, index_path=index_path)
    payload = indexer.index_all(collections=args.collections, write=True)
    printable = {key: value for key, value in payload.items() if key != "documents"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
