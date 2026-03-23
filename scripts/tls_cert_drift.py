#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import socket
import ssl
from datetime import datetime
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from controller_automation_toolkit import load_json, repo_path
from drift_lib import isoformat, utc_now


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
ISSUER_HINTS = {
    "letsencrypt": ("Let's Encrypt", "R11", "E1"),
    "step-ca": ("step", "Smallstep"),
}


def format_certificate_subject(subject: tuple[tuple[tuple[str, str], ...], ...]) -> str:
    flattened: list[str] = []
    for group in subject:
        for key, value in group:
            flattened.append(f"{key}={value}")
    return ", ".join(flattened)


def probe_tls_certificate(host: str, port: int, *, server_name: str | None = None, timeout_seconds: float = 5) -> tuple[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
        with context.wrap_socket(sock, server_hostname=server_name or host) as tls_sock:
            certificate = tls_sock.getpeercert()
    issuer = format_certificate_subject(certificate.get("issuer", ()))
    not_after_raw = certificate.get("notAfter")
    if not not_after_raw:
        raise RuntimeError("certificate missing notAfter field")
    expires = ssl.cert_time_to_seconds(not_after_raw)
    return issuer, expires


def expected_provider_by_host() -> dict[str, str]:
    mapping: dict[str, str] = {}
    payload = load_json(SUBDOMAIN_CATALOG_PATH)
    for entry in payload.get("subdomains", []):
        tls = entry.get("tls", {})
        if not isinstance(tls, dict):
            continue
        provider = str(tls.get("provider", "")).strip()
        if provider:
            mapping[str(entry["fqdn"])] = provider
    return mapping


def collect_drift(*, timeout_seconds: float = 5.0) -> list[dict[str, Any]]:
    provider_map = expected_provider_by_host()
    payload = load_json(SERVICE_CATALOG_PATH)
    now = utc_now()
    records: list[dict[str, Any]] = []
    for service in payload.get("services", []):
        for url_field in ("public_url", "internal_url"):
            url = service.get(url_field)
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                continue
            provider = provider_map.get(host, "")
            try:
                issuer, expires_epoch = probe_tls_certificate(
                    host,
                    parsed.port or 443,
                    server_name=host,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                records.append(
                    {
                        "source": "tls",
                        "event": "platform.drift.critical",
                        "severity": "critical",
                        "service": service["id"],
                        "resource": url,
                        "detail": str(exc),
                        "shared_surfaces": [service["id"], host],
                    }
                )
                continue
            expires_at = datetime.fromtimestamp(expires_epoch, tz=utc_now().tzinfo)
            days_remaining = (expires_at - now).days
            severity = ""
            detail = ""
            if expires_at - now < timedelta(days=7):
                severity = "critical"
                detail = f"certificate expires in {days_remaining} days"
            elif expires_at - now < timedelta(days=14):
                severity = "warn"
                detail = f"certificate expires in {days_remaining} days"

            if provider in ISSUER_HINTS and not any(hint.lower() in issuer.lower() for hint in ISSUER_HINTS[provider]):
                severity = "warn" if severity != "critical" else "critical"
                detail = detail or f"issuer '{issuer}' does not match expected provider {provider}"
            if not severity:
                continue
            records.append(
                {
                    "source": "tls",
                    "event": f"platform.drift.{severity}",
                    "severity": severity,
                    "service": service["id"],
                    "resource": url,
                    "detail": detail,
                    "issuer": issuer,
                    "expected_provider": provider or None,
                    "expires_at": isoformat(expires_at),
                    "shared_surfaces": [service["id"], host],
                }
            )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect TLS certificate expiry and issuer drift.")
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(collect_drift(timeout_seconds=args.timeout), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
