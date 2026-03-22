#!/usr/bin/env python3

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from controller_automation_toolkit import emit_cli_error


DEFAULT_TOKEN_FILE = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/api-token.txt"
)


def read_token(path: Path) -> str:
    token = path.read_text().strip()
    if not token:
        raise ValueError(f"token file is empty: {path}")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the private platform context API.")
    parser.add_argument("--api-url", required=True, help="Platform context API base URL.")
    parser.add_argument(
        "--api-token-file",
        default=str(DEFAULT_TOKEN_FILE),
        help="Bearer token file for the platform context API.",
    )
    parser.add_argument("--question", required=True, help="Natural-language question to retrieve against.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to return.")
    args = parser.parse_args()

    try:
        token = read_token(Path(args.api_token_file).expanduser())
        request = urllib.request.Request(
            args.api_url.rstrip("/") + "/v1/context/query",
            method="POST",
            data=json.dumps({"question": args.question, "top_k": args.top_k}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return emit_cli_error("Platform context query", exc)


if __name__ == "__main__":
    sys.exit(main())
