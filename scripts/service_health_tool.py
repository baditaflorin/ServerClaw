#!/usr/bin/env python3
"""service_health_tool.py — Run health probes from the platform health-probe-catalog.

QUICKSTART FOR LLMs
-------------------
Use this to verify a service is up after deploying it, or to diagnose degradation.
Reads config/health-probe-catalog.json.

IMPORTANT: Most probes use 127.0.0.1 or 10.x (private network) URLs — those are
designed to run FROM INSIDE the VM, not from the controller. This tool will mark
them as "local_only" and provide the exact SSH command to run them manually.

Only public-facing URLs (localhost etc.) are probed directly.

USAGE EXAMPLES
--------------
  # List all services (no SSH needed)
  python3 scripts/service_health_tool.py list

  # List all services on a specific VM
  python3 scripts/service_health_tool.py list --vm docker-runtime

  # Describe a service's full probe config
  python3 scripts/service_health_tool.py describe --service alertmanager

  # Probe a specific service (local_only if private URL)
  python3 scripts/service_health_tool.py probe --service alertmanager

  # Probe all services on a VM
  python3 scripts/service_health_tool.py status-all --vm monitoring

  # Probe everything (takes ~30s, most will be local_only)
  python3 scripts/service_health_tool.py status-all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone

    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from platform.repo import TOPOLOGY_HOST_VARS_PATH
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_CATALOG_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"

_PRIVATE_RE = re.compile(r"https?://(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|100\.)")


def _is_private_url(url: str) -> bool:
    return bool(_PRIVATE_RE.match(url))


def _load_catalog() -> dict[str, Any]:
    if not HEALTH_CATALOG_PATH.exists():
        raise SystemExit(f"Health probe catalog not found: {HEALTH_CATALOG_PATH}")
    return json.loads(HEALTH_CATALOG_PATH.read_text(encoding="utf-8"))


def _load_vm_ip_map() -> dict[str, str]:
    """Build {vm_name: ipv4} from inventory."""
    try:
        import yaml  # type: ignore[import]

        data = yaml.safe_load(TOPOLOGY_HOST_VARS_PATH.read_text(encoding="utf-8"))
        return {v["name"]: v.get("ipv4", "") for v in data.get("proxmox_vms", [])}
    except ImportError:
        pass
    # Fallback regex
    text = TOPOLOGY_HOST_VARS_PATH.read_text(encoding="utf-8")
    vms: dict[str, str] = {}
    current_name = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("name:") and not s.startswith("name: lv3"):
            current_name = s.split(":", 1)[1].strip()
        elif s.startswith("ipv4:") and current_name:
            vms[current_name] = s.split(":", 1)[1].strip()
            current_name = ""
    return vms


def _ssh_suggestion(vm_name: str, url: str, vm_ip_map: dict[str, str]) -> str:
    ip = vm_ip_map.get(vm_name, "10.10.10.X")
    return f"ssh ops@{ip} 'curl -sf --max-time 5 \"{url}\"'"


def _http_probe(url: str, method: str, expected_statuses: list[int], timeout: int) -> dict[str, Any]:
    start = datetime.now(UTC)
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            ok = resp.status in expected_statuses
            return {
                "reachable": True,
                "http_status": resp.status,
                "response_time_ms": elapsed_ms,
                "ok": ok,
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        ok = e.code in expected_statuses
        return {"reachable": True, "http_status": e.code, "response_time_ms": elapsed_ms, "ok": ok}
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        return {"reachable": False, "error": str(e), "ok": False}


def _probe_service_kind(
    service_name: str,
    probe: dict[str, Any],
    probe_kind: str,
    vm_name: str,
    vm_ip_map: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    url = probe.get("url", "")
    method = probe.get("method", "GET")
    expected = probe.get("expected_status", [200])
    kind = probe.get("kind", "http")

    if kind != "http" or not url:
        return {
            "service": service_name,
            "probe_kind": probe_kind,
            "status": "unsupported",
            "note": f"Probe kind '{kind}' is not HTTP — run via ansible role verify task.",
        }

    if _is_private_url(url):
        return {
            "service": service_name,
            "probe_kind": probe_kind,
            "status": "local_only",
            "url": url,
            "note": "Private network endpoint — must be probed from inside the guest VM.",
            "suggested_ssh_command": _ssh_suggestion(vm_name, url, vm_ip_map),
        }

    result = _http_probe(url, method, expected, min(timeout, probe.get("timeout_seconds", 10)))
    return {
        "service": service_name,
        "probe_kind": probe_kind,
        "status": "ok" if result.get("ok") else "fail",
        "url": url,
        "http_status": result.get("http_status"),
        "response_time_ms": result.get("response_time_ms"),
        "reachable": result.get("reachable"),
        "error": result.get("error"),
    }


def cmd_list(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    rows = []
    for name, svc in catalog["services"].items():
        if args.vm and svc.get("owning_vm", "") != args.vm:
            continue
        rows.append(
            {
                "service_name": name,
                "owning_vm": svc.get("owning_vm"),
                "role": svc.get("role"),
                "probe_types": [pt for pt in ("startup", "liveness", "readiness") if pt in svc],
            }
        )
    rows.sort(key=lambda x: (x["owning_vm"] or "", x["service_name"]))
    print(json.dumps({"services": rows, "count": len(rows)}, indent=2))
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    svcs = catalog["services"]
    if args.service not in svcs:
        # fuzzy match
        matches = [k for k in svcs if args.service.lower() in k.lower()]
        if len(matches) == 1:
            args.service = matches[0]
        elif matches:
            raise SystemExit(f"Ambiguous: {matches}. Be more specific.")
        else:
            raise SystemExit(f"Service '{args.service}' not found.")
    print(json.dumps(svcs[args.service], indent=2))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    svcs = catalog["services"]
    if args.service not in svcs:
        matches = [k for k in svcs if args.service.lower() in k.lower()]
        if len(matches) == 1:
            args.service = matches[0]
        elif matches:
            raise SystemExit(f"Ambiguous: {matches}")
        else:
            raise SystemExit(f"Service '{args.service}' not found.")

    svc = svcs[args.service]
    vm_ip_map = _load_vm_ip_map()
    vm_name = svc.get("owning_vm", "")

    probe_kinds = [args.kind] if args.kind else [pt for pt in ("liveness", "readiness", "startup") if pt in svc]
    results = []
    for pk in probe_kinds:
        if pk not in svc:
            results.append({"service": args.service, "probe_kind": pk, "status": "not_configured"})
            continue
        result = _probe_service_kind(args.service, svc[pk], pk, vm_name, vm_ip_map, args.timeout)
        results.append(result)

    print(json.dumps({"service": args.service, "owning_vm": vm_name, "probes": results}, indent=2))
    return 0 if all(r.get("status") in ("ok", "local_only", "unsupported") for r in results) else 2


def cmd_status_all(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    vm_ip_map = _load_vm_ip_map()
    all_services = [
        (name, svc) for name, svc in catalog["services"].items() if not args.vm or svc.get("owning_vm") == args.vm
    ]

    def _probe_one(name: str, svc: dict) -> dict:
        vm_name = svc.get("owning_vm", "")
        # prefer liveness, fall back to startup
        for pk in ("liveness", "startup"):
            if pk in svc:
                return _probe_service_kind(name, svc[pk], pk, vm_name, vm_ip_map, 5)
        return {"service": name, "probe_kind": "none", "status": "not_configured"}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_probe_one, name, svc): name for name, svc in all_services}
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: (x.get("status", ""), x.get("service", "")))
    counts = {
        s: sum(1 for r in results if r.get("status") == s)
        for s in ("ok", "fail", "local_only", "unsupported", "not_configured", "unknown")
    }

    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "results": results,
                "summary": {k: v for k, v in counts.items() if v > 0},
                "total": len(results),
            },
            indent=2,
        )
    )
    failing = [r for r in results if r.get("status") == "fail"]
    return 2 if failing else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="service_health_tool.py",
        description="Run health probes from the platform health-probe-catalog.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    p_list = subs.add_parser("list", help="List all services and their probe types.")
    p_list.add_argument("--vm", help="Filter by owning VM name.")

    p_desc = subs.add_parser("describe", help="Show full probe config for a service.")
    p_desc.add_argument("--service", required=True)

    p_probe = subs.add_parser("probe", help="Probe a specific service.")
    p_probe.add_argument("--service", required=True)
    p_probe.add_argument("--kind", choices=["liveness", "readiness", "startup"])
    p_probe.add_argument("--timeout", type=int, default=10, metavar="SEC")

    p_all = subs.add_parser("status-all", help="Probe all services (or all on a VM).")
    p_all.add_argument("--vm", help="Filter by owning VM name.")

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "list":
            return cmd_list(args)
        if args.command == "describe":
            return cmd_describe(args)
        if args.command == "probe":
            return cmd_probe(args)
        if args.command == "status-all":
            return cmd_status_all(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
