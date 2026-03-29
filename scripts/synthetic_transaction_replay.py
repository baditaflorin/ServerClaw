#!/usr/bin/env python3
"""Replay privacy-safe synthetic transactions against declared validation targets."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


DEFAULT_CATALOG_PATH = repo_path("config", "synthetic-transaction-catalog.json")


@dataclass(frozen=True)
class CommandOutcome:
    returncode: int
    stdout: str
    stderr: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_executor(command: str) -> CommandOutcome:
    completed = subprocess.run(
        ["/bin/bash", "-lc", command],
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandOutcome(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _compact(text: str, *, limit: int = 200) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _percentile(samples: list[int], percentile: float) -> int:
    if not samples:
        return 0
    ordered = sorted(samples)
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return ordered[rank - 1]


def _latency_summary(samples: list[int]) -> dict[str, int]:
    return {
        "count": len(samples),
        "p50": _percentile(samples, 50),
        "p95": _percentile(samples, 95),
        "max": max(samples) if samples else 0,
    }


def _catalog_ref(path: Path) -> str:
    try:
        return str(path.relative_to(repo_path()))
    except ValueError:
        return str(path)


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("schema_version") != "1.0":
        raise ValueError(f"{path.name}: unsupported schema_version {payload.get('schema_version')!r}")
    targets = payload.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise ValueError(f"{path.name}: targets must be a non-empty object")
    return payload


def load_target_profile(target_id: str, *, catalog_path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    profile = catalog["targets"].get(target_id)
    if not isinstance(profile, dict):
        raise ValueError(f"unknown synthetic replay target: {target_id}")
    scenarios = profile.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"synthetic replay target {target_id!r} must define at least one scenario")
    return profile


def _extract_json_payload(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _build_http_probe_command(request: dict[str, Any]) -> str:
    url = str(request["url"])
    method = str(request.get("method", "GET"))
    timeout_seconds = int(request.get("timeout_seconds", 10))
    expected_status = [int(item) for item in request.get("expected_status", [200])]
    headers = request.get("headers", {})
    expect_body_contains = [str(item) for item in request.get("expect_body_contains", [])]
    return (
        "python3 - <<'PY'\n"
        "import json\n"
        "import sys\n"
        "import time\n"
        "import urllib.error\n"
        "import urllib.request\n"
        f"url = {url!r}\n"
        f"method = {method!r}\n"
        f"timeout_seconds = {timeout_seconds}\n"
        f"expected_status = {expected_status!r}\n"
        f"headers = {headers!r}\n"
        f"expect_body_contains = {expect_body_contains!r}\n"
        "started = time.perf_counter()\n"
        "request = urllib.request.Request(url, method=method, headers=headers)\n"
        "try:\n"
        "    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:\n"
        "        body = response.read().decode('utf-8', 'replace')\n"
        "        status = response.status\n"
        "except urllib.error.HTTPError as exc:\n"
        "    body = exc.read().decode('utf-8', 'replace')\n"
        "    status = exc.code\n"
        "except Exception as exc:\n"
        "    elapsed_ms = int((time.perf_counter() - started) * 1000)\n"
        "    print(json.dumps({'status': None, 'elapsed_ms': elapsed_ms, 'error': str(exc)}))\n"
        "    sys.exit(1)\n"
        "elapsed_ms = int((time.perf_counter() - started) * 1000)\n"
        "missing = [needle for needle in expect_body_contains if needle not in body]\n"
        "payload = {\n"
        "    'status': status,\n"
        "    'elapsed_ms': elapsed_ms,\n"
        "    'body_excerpt': body[:240],\n"
        "    'missing_contains': missing,\n"
        "}\n"
        "print(json.dumps(payload))\n"
        "sys.exit(0 if status in expected_status and not missing else 1)\n"
        "PY"
    )


def _build_command_probe_command(scenario: dict[str, Any]) -> str:
    command = str(scenario["command"])
    expect_stdout_contains = [str(item) for item in scenario.get("expect_stdout_contains", [])]
    return (
        "python3 - <<'PY'\n"
        "import json\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        f"command = {command!r}\n"
        f"expect_stdout_contains = {expect_stdout_contains!r}\n"
        "started = time.perf_counter()\n"
        "completed = subprocess.run(['/bin/bash', '-lc', command], text=True, capture_output=True, check=False)\n"
        "elapsed_ms = int((time.perf_counter() - started) * 1000)\n"
        "stdout = completed.stdout or ''\n"
        "missing = [needle for needle in expect_stdout_contains if needle not in stdout]\n"
        "payload = {\n"
        "    'returncode': completed.returncode,\n"
        "    'elapsed_ms': elapsed_ms,\n"
        "    'stdout_excerpt': stdout[:240],\n"
        "    'stderr_excerpt': (completed.stderr or '')[:240],\n"
        "    'missing_contains': missing,\n"
        "}\n"
        "print(json.dumps(payload))\n"
        "sys.exit(0 if completed.returncode == 0 and not missing else 1)\n"
        "PY"
    )


def build_probe_command(scenario: dict[str, Any]) -> str:
    kind = str(scenario.get("kind", "http"))
    if kind == "http":
        request = scenario.get("request")
        if not isinstance(request, dict) or "url" not in request:
            raise ValueError(f"scenario {scenario.get('id')!r} must define request.url")
        return _build_http_probe_command(request)
    if kind == "command":
        if "command" not in scenario:
            raise ValueError(f"scenario {scenario.get('id')!r} must define command")
        return _build_command_probe_command(scenario)
    raise ValueError(f"unsupported synthetic replay scenario kind: {kind}")


def _scenario_queue_depth(scenario: dict[str, Any]) -> dict[str, Any]:
    queue_depth = scenario.get("queue_depth")
    if isinstance(queue_depth, dict):
        return queue_depth
    return {
        "status": "not_applicable",
        "detail": "This scenario does not declare a queue or backlog probe.",
    }


def run_scenario(
    scenario: dict[str, Any],
    *,
    execute_command,
) -> dict[str, Any]:
    command = build_probe_command(scenario)
    total_iterations = int(scenario.get("iterations", 1))
    minimum_success_rate = float(scenario.get("minimum_success_rate", 1.0))
    requests: list[dict[str, Any]] = []
    latencies: list[int] = []
    success_count = 0

    for iteration in range(1, total_iterations + 1):
        started = time.perf_counter()
        outcome = execute_command(command)
        payload = _extract_json_payload(outcome.stdout)
        latency_ms = int(payload.get("elapsed_ms", round((time.perf_counter() - started) * 1000)))
        latencies.append(latency_ms)
        status = "pass" if outcome.returncode == 0 else "fail"
        if status == "pass":
            success_count += 1
        requests.append(
            {
              "iteration": iteration,
              "status": status,
              "latency_ms": latency_ms,
              "observed_status": payload.get("status", payload.get("returncode")),
              "observed": _compact(
                  payload.get("body_excerpt")
                  or payload.get("stdout_excerpt")
                  or payload.get("error")
                  or outcome.stdout
                  or outcome.stderr
              ),
              "stderr": _compact(payload.get("stderr_excerpt") or outcome.stderr),
            }
        )

    success_rate = success_count / total_iterations if total_iterations else 0.0
    overall = "pass" if success_rate >= minimum_success_rate else "fail"
    return {
        "id": str(scenario["id"]),
        "name": str(scenario.get("name", scenario["id"])),
        "kind": str(scenario.get("kind", "http")),
        "required": bool(scenario.get("required", True)),
        "iterations": total_iterations,
        "success_count": success_count,
        "request_count": total_iterations,
        "success_rate": round(success_rate, 4),
        "minimum_success_rate": minimum_success_rate,
        "latency_ms": _latency_summary(latencies),
        "queue_depth": _scenario_queue_depth(scenario),
        "overall": overall,
        "requests": requests,
    }


def run_target_profile(
    target_id: str,
    *,
    execute_command=_local_executor,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
) -> dict[str, Any]:
    profile = load_target_profile(target_id, catalog_path=catalog_path)
    scenarios = [run_scenario(item, execute_command=execute_command) for item in profile["scenarios"]]
    request_count = sum(item["request_count"] for item in scenarios)
    success_count = sum(item["success_count"] for item in scenarios)
    latencies = [request["latency_ms"] for item in scenarios for request in item["requests"]]
    required_failures = [item for item in scenarios if item["required"] and item["overall"] != "pass"]
    overall = "pass" if not required_failures else "fail"
    success_rate = success_count / request_count if request_count else 0.0
    validation_window = profile.get("validation_window", {})
    window_name = validation_window.get("name", "steady_state")
    window_detail = validation_window.get("detail", "Synthetic replay executed without a declared validation window.")
    summary = (
        f"{success_count}/{request_count} synthetic requests passed across "
        f"{len(scenarios)} scenarios on target {target_id!r}"
    )
    return {
        "schema_version": "1.0",
        "executed_at": isoformat(utc_now()),
        "catalog_path": _catalog_ref(catalog_path),
        "target_id": target_id,
        "target_name": str(profile.get("name", target_id)),
        "target_description": str(profile.get("description", "")),
        "overall": overall,
        "summary": summary,
        "success_count": success_count,
        "request_count": request_count,
        "success_rate": round(success_rate, 4),
        "latency_ms": _latency_summary(latencies),
        "queue_depth": profile.get(
            "queue_depth",
            {
                "status": "not_applicable",
                "detail": "No queue or backlog probes are declared for this target profile.",
            },
        ),
        "window_assessment": {
            "window": window_name,
            "status": "pass" if overall == "pass" else "fail",
            "detail": window_detail,
        },
        "scenarios": scenarios,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-report-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_target_profile(args.target, catalog_path=args.catalog)
        if args.dry_run:
            payload = {
                "target_id": args.target,
                "target_name": profile.get("name", args.target),
                "scenario_ids": [item["id"] for item in profile["scenarios"]],
                "queue_depth": profile.get("queue_depth"),
                "validation_window": profile.get("validation_window"),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        report = run_target_profile(args.target, catalog_path=args.catalog)
        print(
            json.dumps(
                {
                    "summary": report["summary"],
                    "overall": report["overall"],
                    "latency_ms": report["latency_ms"],
                    "window_assessment": report["window_assessment"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
        return 0 if report["overall"] == "pass" else 1
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("synthetic transaction replay", exc)


if __name__ == "__main__":
    raise SystemExit(main())
