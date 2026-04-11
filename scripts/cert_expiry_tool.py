#!/usr/bin/env python3
"""cert_expiry_tool.py — Scan TLS endpoints for certificate expiry.

QUICKSTART FOR LLMs
-------------------
ADR 0101 identifies certificate expiry as a "notorious operational failure mode."
This tool reads config/certificate-catalog.json and probes each endpoint.

NOTE: Endpoints on private IPs (10.x, 192.168.x) are unreachable from the
controller and will be reported as "unknown" — that is expected, not an error.
Only public endpoints (localhost domains, etc.) can be probed from here.

USAGE EXAMPLES
--------------
  # Scan all certificates (public + private)
  python3 scripts/cert_expiry_tool.py scan

  # Scan a specific cert
  python3 scripts/cert_expiry_tool.py scan --id build-edge

  # Full report sorted by days remaining
  python3 scripts/cert_expiry_tool.py report

  # Show catalog entry + live probe for one cert
  python3 scripts/cert_expiry_tool.py show --id build-edge

EXIT CODES
----------
  0 — all reachable certs ok
  1 — error (file missing, bad args)
  2 — at least one cert is warn or critical
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CERT_CATALOG_PATH = REPO_ROOT / "config" / "certificate-catalog.json"

_PRIVATE_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "100.",
    "127.",
    "fd",
    "::1",
)


def _is_private(host: str) -> bool:
    return any(host.startswith(p) for p in _PRIVATE_PREFIXES)


def _load_catalog() -> dict[str, Any]:
    if not CERT_CATALOG_PATH.exists():
        raise SystemExit(f"Certificate catalog not found: {CERT_CATALOG_PATH}")
    return json.loads(CERT_CATALOG_PATH.read_text(encoding="utf-8"))


def _probe_cert(host: str, port: int, server_name: str, timeout: int = 5) -> dict[str, Any]:
    if _is_private(host):
        return {
            "reachable": False,
            "reason": "private_network",
            "note": f"Endpoint {host}:{port} is on a private network — probe from inside the guest.",
        }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=server_name) as ssock:
                cert = ssock.getpeercert()
                not_after = cert.get("notAfter", "")
                expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
                days_left = (expiry - datetime.now(UTC)).days
                subject = dict(x[0] for x in cert.get("subject", []) if len(x[0]) == 2)
                issuer = dict(x[0] for x in cert.get("issuer", []) if len(x[0]) == 2)
                return {
                    "reachable": True,
                    "expiry": expiry.isoformat(),
                    "days_left": days_left,
                    "subject": subject,
                    "issuer_cn": issuer.get("commonName", ""),
                }
    except TimeoutError:
        return {"reachable": False, "reason": "timeout"}
    except ConnectionRefusedError:
        return {"reachable": False, "reason": "connection_refused"}
    except OSError as e:
        return {"reachable": False, "reason": str(e)}


def _classify(probe: dict, policy: dict) -> str:
    if not probe.get("reachable"):
        return "unknown"
    days = probe.get("days_left", 9999)
    if days <= policy.get("critical_days", 14):
        return "critical"
    if days <= policy.get("warn_days", 21):
        return "warn"
    return "ok"


def _scan_one(cert: dict[str, Any], timeout: int) -> dict[str, Any]:
    ep = cert.get("endpoint", {})
    policy = cert.get("policy", {"warn_days": 21, "critical_days": 14})
    probe = _probe_cert(ep.get("host", ""), ep.get("port", 443), ep.get("server_name", ep.get("host", "")), timeout)
    status = _classify(probe, policy)
    return {
        "id": cert["id"],
        "service_id": cert.get("service_id", ""),
        "summary": cert.get("summary", ""),
        "endpoint": f"{ep.get('host')}:{ep.get('port')}",
        "status": status,
        "days_left": probe.get("days_left"),
        "expiry": probe.get("expiry"),
        "reachable": probe.get("reachable"),
        "probe_note": probe.get("note") or probe.get("reason"),
        "policy": policy,
        "renewal_agent": cert.get("renewal", {}).get("agent", ""),
        "managed_by_repo": cert.get("renewal", {}).get("managed_by_repo", False),
    }


def cmd_scan(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    certs = [c for c in catalog["certificates"] if c.get("status") == "active"]
    if args.id:
        certs = [c for c in certs if c["id"] == args.id]
        if not certs:
            raise SystemExit(f"Certificate '{args.id}' not found or not active.")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_scan_one, c, args.timeout): c["id"] for c in certs}
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: x.get("days_left") or 9999)
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "critical", "unknown")}
    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "results": results,
                "summary": summary,
            },
            indent=2,
        )
    )
    return 2 if summary["warn"] + summary["critical"] > 0 else 0


def cmd_report(args: argparse.Namespace) -> int:
    # Same as scan but adds a human_summary field
    catalog = _load_catalog()
    certs = [c for c in catalog["certificates"] if c.get("status") == "active"]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_scan_one, c, 5): c["id"] for c in certs}
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda x: x.get("days_left") or 9999)
    critical = [r for r in results if r["status"] == "critical"]
    warn = [r for r in results if r["status"] == "warn"]
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "critical", "unknown")}
    lines = []
    if critical:
        lines.append(
            f"CRITICAL ({len(critical)}): " + ", ".join(f"{r['id']} ({r.get('days_left', '?')}d)" for r in critical)
        )
    if warn:
        lines.append(f"WARN ({len(warn)}): " + ", ".join(f"{r['id']} ({r.get('days_left', '?')}d)" for r in warn))
    if not critical and not warn:
        reachable_ok = [r for r in results if r["status"] == "ok"]
        lines.append(f"All {len(reachable_ok)} reachable certs OK.")
    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "results": results,
                "summary": summary,
                "human_summary": " | ".join(lines) if lines else "No reachable certs found.",
            },
            indent=2,
        )
    )
    return 2 if summary["warn"] + summary["critical"] > 0 else 0


def cmd_show(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    matches = [c for c in catalog["certificates"] if c["id"] == args.id]
    if not matches:
        raise SystemExit(f"Certificate '{args.id}' not found.")
    cert = matches[0]
    ep = cert.get("endpoint", {})
    probe = _probe_cert(ep.get("host", ""), ep.get("port", 443), ep.get("server_name", ep.get("host", "")), timeout=5)
    policy = cert.get("policy", {"warn_days": 21, "critical_days": 14})
    print(
        json.dumps(
            {
                "catalog_entry": cert,
                "live_probe": {**probe, "status": _classify(probe, policy)},
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cert_expiry_tool.py",
        description="Scan TLS endpoints from certificate catalog for expiry.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    p_scan = subs.add_parser("scan", help="Probe all (or one) active certs.")
    p_scan.add_argument("--id", help="Probe only this cert id.")
    p_scan.add_argument("--timeout", type=int, default=5, metavar="SEC")

    subs.add_parser("report", help="Full report sorted by days remaining.")

    p_show = subs.add_parser("show", help="Catalog entry + live probe for one cert.")
    p_show.add_argument("--id", required=True)

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "scan":
            return cmd_scan(args)
        if args.command == "report":
            return cmd_report(args)
        if args.command == "show":
            return cmd_show(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
