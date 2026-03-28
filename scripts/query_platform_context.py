#!/usr/bin/env python3

import argparse
import json
import sys

from controller_automation_toolkit import emit_cli_error
from platform.llm.retrieval import PlatformContextRetriever, default_platform_context_token_file, default_platform_context_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the private platform context API.")
    parser.add_argument(
        "--api-url",
        default=default_platform_context_url(),
        help="Platform context API base URL.",
    )
    parser.add_argument(
        "--api-token-file",
        default=str(default_platform_context_token_file()),
        help="Bearer token file for the platform context API.",
    )
    parser.add_argument("--question", required=True, help="Natural-language question to retrieve against.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to return.")
    args = parser.parse_args()

    try:
        retriever = PlatformContextRetriever(
            api_url=args.api_url,
            token_file=args.api_token_file,
            timeout_seconds=120,
        )
        print(json.dumps(retriever.retrieve_payload(args.question, top_k=args.top_k), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Platform context query", exc)


if __name__ == "__main__":
    sys.exit(main())
