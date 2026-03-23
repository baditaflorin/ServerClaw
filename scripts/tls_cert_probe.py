#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import socket
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, repo_path


CERTIFICATE_CATALOG_PATH = repo_path("config", "certificate-catalog.json")
ISSUER_HINTS = {
    "letsencrypt": ("Let's Encrypt", "R11", "E1"),
    "step-ca": ("step", "Smallstep", "LV3 Internal CA"),
}


def format_certificate_name(subject: tuple[tuple[tuple[str, str], ...], ...]) -> str:
    flattened: list[str] = []
    for group in subject:
        for key, value in group:
            flattened.append(f"{key}={value}")
    return ", ".join(flattened)


def probe_tls_certificate(
    host: str,
    port: int,
    *,
    server_name: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
        with context.wrap_socket(sock, server_hostname=server_name or host) as tls_sock:
            certificate = tls_sock.getpeercert()
    not_after_raw = certificate.get("notAfter")
    if not not_after_raw:
        raise RuntimeError("certificate missing notAfter field")
    return {
        "subject": format_certificate_name(certificate.get("subject", ())),
        "issuer": format_certificate_name(certificate.get("issuer", ())),
        "not_after": datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after_raw), tz=UTC),
    }


def load_certificate_catalog(path: Path = CERTIFICATE_CATALOG_PATH) -> list[dict[str, Any]]:
    payload = load_json(path)
    certificates = payload.get("certificates")
    if not isinstance(certificates, list):
        raise ValueError("config/certificate-catalog.json must define a certificates list")
    return certificates


def expected_issuer_matches(expected_issuer: str, issuer: str, subject: str) -> bool:
    if expected_issuer == "any":
        return True
    if expected_issuer == "self-signed":
        return issuer == subject
    hints = ISSUER_HINTS.get(expected_issuer)
    if not hints:
        return True
    issuer_lower = issuer.lower()
    return any(hint.lower() in issuer_lower for hint in hints)


def evaluate_certificate(
    certificate: dict[str, Any],
    *,
    timeout_seconds: float = 5.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(tz=UTC)
    endpoint = certificate["endpoint"]
    policy = certificate["policy"]
    result = {
        "certificate_id": certificate["id"],
        "service_id": certificate["service_id"],
        "summary": certificate["summary"],
    }
    try:
        observed = probe_tls_certificate(
            endpoint["host"],
            int(endpoint["port"]),
            server_name=endpoint.get("server_name"),
            timeout_seconds=timeout_seconds,
        )
    except (OSError, RuntimeError, ValueError, ssl.SSLError) as exc:
        result["status"] = "probe_failed"
        result["severity"] = "critical"
        result["error"] = str(exc)
        return result

    days_remaining = int((observed["not_after"] - now).total_seconds() // 86400)
    result.update(
        {
            "subject": observed["subject"],
            "issuer": observed["issuer"],
            "not_after": observed["not_after"].isoformat().replace("+00:00", "Z"),
            "days_remaining": days_remaining,
        }
    )

    if not expected_issuer_matches(certificate["expected_issuer"], observed["issuer"], observed["subject"]):
        result["status"] = "issuer_mismatch"
        result["severity"] = "warning"
        result["expected_issuer"] = certificate["expected_issuer"]
        return result

    if days_remaining < int(policy["critical_days"]):
        result["status"] = "expiring_critical"
        result["severity"] = "critical"
        return result
    if days_remaining < int(policy["warn_days"]):
        result["status"] = "expiring_warning"
        result["severity"] = "warning"
        return result

    result["status"] = "ok"
    result["severity"] = "ok"
    return result


def collect_certificate_results(
    certificates: list[dict[str, Any]] | None = None,
    *,
    timeout_seconds: float = 5.0,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    certificates = certificates or load_certificate_catalog()
    results = [
        evaluate_certificate(certificate, timeout_seconds=timeout_seconds, now=now)
        for certificate in certificates
        if certificate.get("status") == "active"
    ]
    results.sort(key=lambda item: item["certificate_id"])
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe every active certificate in the LV3 certificate catalog.")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--certificate-id", dest="certificate_ids", action="append")
    parser.add_argument("--fail-on", choices=["warning", "critical", "never"], default="critical")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    certificates = load_certificate_catalog()
    if args.certificate_ids:
        selected = set(args.certificate_ids)
        certificates = [entry for entry in certificates if entry["id"] in selected]
    results = collect_certificate_results(certificates, timeout_seconds=args.timeout)
    print(json.dumps(results, indent=2))
    if args.fail_on == "never":
        return 0
    if args.fail_on == "warning" and any(item["severity"] in {"warning", "critical"} for item in results):
        return 1
    if args.fail_on == "critical" and any(item["severity"] == "critical" for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
