#!/usr/bin/env python3

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from controller_automation_toolkit import REPO_ROOT, emit_cli_error
from platform_context_corpus import build_chunks, build_manifest_from_chunks, filter_chunks_by_source_paths


DEFAULT_TOKEN_FILE = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/api-token.txt"
)


def read_token(path: Path) -> str:
    token = path.read_text().strip()
    if not token:
        raise ValueError(f"token file is empty: {path}")
    return token


def api_post(url: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the repo-grounded platform context chunk set and optionally upload it."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to index.")
    parser.add_argument("--api-url", help="Platform context API base URL, for example http://100.118.189.95:8010.")
    parser.add_argument(
        "--api-token-file",
        default=str(DEFAULT_TOKEN_FILE),
        help="Bearer token file for the platform context API.",
    )
    parser.add_argument("--max-chars", type=int, default=2400, help="Maximum chunk size in characters.")
    parser.add_argument("--overlap-chars", type=int, default=240, help="Chunk overlap in characters.")
    parser.add_argument("--dry-run", action="store_true", help="Build and summarize the chunk set without uploading.")
    parser.add_argument(
        "--include-path",
        action="append",
        default=[],
        help="Limit the uploaded chunk set to the given repo-relative path or directory prefix. Repeat as needed.",
    )
    parser.add_argument(
        "--write-manifest",
        help="Optional path to write the computed chunk manifest JSON.",
    )
    args = parser.parse_args()

    try:
        repo_root = Path(args.repo_root).resolve()
        chunks = build_chunks(repo_root, max_chars=args.max_chars, overlap_chars=args.overlap_chars)
        chunks = filter_chunks_by_source_paths(chunks, args.include_path)
        manifest = build_manifest_from_chunks(
            chunks,
            repo_root=repo_root,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        )
        if args.write_manifest:
            Path(args.write_manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        if args.dry_run:
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return 0

        if not args.api_url:
            raise ValueError("--api-url is required unless --dry-run is set")

        token = read_token(Path(args.api_token_file).expanduser())
        result = api_post(
            args.api_url.rstrip("/") + "/v1/admin/rebuild",
            token,
            {
                "replace": True,
                "chunks": chunks,
                "manifest": manifest,
            },
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return emit_cli_error("RAG index build", exc)


if __name__ == "__main__":
    sys.exit(main())
