#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from browser_runner_client import build_headers, read_secret, run_session


def build_smoke_payload() -> dict[str, Any]:
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>LV3 Browser Runner Smoke</title>
    <script>
      function applyGreeting() {
        const raw = document.getElementById("name").value.trim();
        document.getElementById("result").textContent = raw.toUpperCase();
      }
    </script>
  </head>
  <body>
    <main>
      <h1>LV3 Browser Runner Smoke</h1>
      <label for="name">Name</label>
      <input id="name" type="text" value="">
      <button id="apply" type="button" onclick="applyGreeting()">Apply</button>
      <p id="result">PENDING</p>
    </main>
  </body>
</html>
""".strip()
    data_url = "data:text/html;charset=utf-8," + quote(html)
    return {
        "url": data_url,
        "steps": [
            {"action": "fill", "selector": "#name", "value": "browser runner", "timeout_seconds": 15},
            {"action": "click", "selector": "#apply", "timeout_seconds": 15},
            {"action": "wait_for_selector", "selector": "#result", "state": "visible", "timeout_seconds": 15},
        ],
        "selectors": [
            {"name": "heading", "selector": "h1"},
            {"name": "result", "selector": "#result"},
        ],
        "capture_screenshot": True,
        "capture_pdf": True,
        "timeout_seconds": 30,
    }


def selector_text(result: dict[str, Any], name: str) -> str:
    for item in result.get("selector_results", []):
        if item.get("name") == name:
            return str(item.get("text", ""))
    raise RuntimeError(f"selector result {name!r} is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded smoke session against the browser runner.")
    parser.add_argument("--base-url", required=True, help="Browser runner or gateway base URL")
    parser.add_argument("--output-path", help="Optional path to write the smoke result JSON")
    parser.add_argument("--api-key-file", help="Optional API key file")
    parser.add_argument("--api-key-header", default="X-LV3-Dify-Api-Key")
    parser.add_argument("--bearer-token-file", help="Optional bearer token file")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    api_key = read_secret(args.api_key_file) if args.api_key_file else None
    bearer_token = read_secret(args.bearer_token_file) if args.bearer_token_file else None
    payload = build_smoke_payload()
    result = run_session(
        args.base_url,
        payload,
        timeout_seconds=args.timeout_seconds,
        headers=build_headers(api_key=api_key, api_key_header=args.api_key_header, bearer_token=bearer_token),
    )

    if selector_text(result, "heading") != "LV3 Browser Runner Smoke":
        raise RuntimeError("browser runner smoke heading did not match the expected title")
    if selector_text(result, "result") != "BROWSER RUNNER":
        raise RuntimeError("browser runner smoke action flow did not produce the expected uppercase result")
    if not result.get("artifacts"):
        raise RuntimeError("browser runner smoke did not produce any artifacts")

    rendered = json.dumps(result, indent=2) + "\n"
    if args.output_path:
        output_path = Path(args.output_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
