#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path

import yaml


def load_default_model(repo_root: Path) -> str:
    payload = yaml.safe_load((repo_root / "config" / "ollama-models.yaml").read_text(encoding="utf-8")) or {}
    for item in payload.get("models", []):
        if isinstance(item, dict) and item.get("pull_on_startup"):
            name = str(item.get("name", "")).strip()
            if name:
                return name
    raise SystemExit("config/ollama-models.yaml does not define a pull_on_startup model")


def post_json(url: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark a local Ollama model.")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model")
    parser.add_argument("--prompt", default="Summarize the value of private local inference in one short sentence.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    model = args.model or load_default_model(repo_root)
    latencies_ms: list[float] = []
    last_response = ""

    for _ in range(args.runs):
        started = time.monotonic()
        payload = post_json(
            f"{args.base_url.rstrip('/')}/api/generate",
            {
                "model": model,
                "prompt": args.prompt,
                "stream": False,
                "options": {"num_predict": args.max_tokens, "temperature": 0},
            },
            timeout=args.timeout,
        )
        latencies_ms.append((time.monotonic() - started) * 1000)
        last_response = str(payload.get("response", "")).strip()

    summary = {
        "base_url": args.base_url,
        "model": model,
        "runs": args.runs,
        "latency_ms": {
            "min": round(min(latencies_ms), 1),
            "avg": round(statistics.mean(latencies_ms), 1),
            "p95": round(percentile(latencies_ms, 0.95), 1),
            "max": round(max(latencies_ms), 1),
        },
        "last_response": last_response,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Model: {summary['model']}")
        print(f"Runs:  {summary['runs']}")
        print(
            "Latency ms:"
            f" min={summary['latency_ms']['min']}"
            f" avg={summary['latency_ms']['avg']}"
            f" p95={summary['latency_ms']['p95']}"
            f" max={summary['latency_ms']['max']}"
        )
        print(f"Last response: {summary['last_response']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
