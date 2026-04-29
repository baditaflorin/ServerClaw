#!/usr/bin/env python3
"""Pre-converge live-state check: DNS resolution + cert SAN match.

ADR 0467 — extends the existing converge_dry_run.py (ws-0445) with
live-state probes that catch drift the static gate cannot see.

For each service in `catalog/services/<svc>/service.yaml` with a
public hostname:

  - DNS: `socket.gethostbyname(fqdn)` and report whether the resolved
    IP matches the topology's expected public-edge IP (when the
    service is published through the nginx edge).
  - Cert SAN: TLS-handshake to port 443 and confirm the cert's SAN
    list covers the FQDN.

The script does NOT attempt to fix anything. It writes a single
JSON report (or human-readable summary) and returns 0 on full
coverage, 1 on any drift, 2 on usage error.

Composes with ADR 0463 (post-converge health probes) — same
catalog input, same receipt-shape conventions.

Usage:

    python3 scripts/preconverge_live_check.py --service <slug>...
    python3 scripts/preconverge_live_check.py --all
    python3 scripts/preconverge_live_check.py --all --json
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "catalog" / "services"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML required") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text()) or {}


def _list_services() -> list[str]:
    if not CATALOG_DIR.is_dir():
        return []
    return sorted(p.name for p in CATALOG_DIR.iterdir() if p.is_dir() and (p / "service.yaml").is_file())


def _service_public_fqdn(slug: str) -> str | None:
    """Pull the canonical public FQDN from the service catalog."""
    try:
        data = _load_yaml(CATALOG_DIR / slug / "service.yaml")
    except FileNotFoundError:
        return None
    svc = data.get("service") or {}
    sub = svc.get("subdomain") or ""
    if not sub:
        return None
    sub = str(sub).strip()
    return sub or None


def check_dns(fqdn: str, expected_ips: list[str] | None = None) -> dict:
    """Resolve FQDN → IP. When expected_ips is non-empty, also assert membership."""
    try:
        resolved = socket.gethostbyname(fqdn)
    except OSError as exc:
        return {
            "fqdn": fqdn,
            "ok": False,
            "kind": "dns",
            "detail": f"resolution failed: {exc}",
            "resolved": None,
        }
    if expected_ips and resolved not in expected_ips:
        return {
            "fqdn": fqdn,
            "ok": False,
            "kind": "dns",
            "detail": f"resolved {resolved} not in expected {expected_ips}",
            "resolved": resolved,
        }
    return {"fqdn": fqdn, "ok": True, "kind": "dns", "detail": f"resolved {resolved}", "resolved": resolved}


def _cert_sans(fqdn: str, port: int = 443, timeout: float = 5.0) -> tuple[list[str], str | None]:
    """Return (san_dns_list, error). Untrusted cert is fine — we only inspect SANs."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((fqdn, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=fqdn) as sock:
                cert = sock.getpeercert(binary_form=False) or {}
        sans = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
        # Without proper verify the server may not return getpeercert content;
        # fall back to binary form parsing if needed.
        if not sans:
            with socket.create_connection((fqdn, port), timeout=timeout) as raw:
                with ctx.wrap_socket(raw, server_hostname=fqdn) as sock:
                    der = sock.getpeercert(binary_form=True)
            try:
                from cryptography import x509  # type: ignore

                cert_obj = x509.load_der_x509_certificate(der)
                ext = cert_obj.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                sans = list(ext.value.get_values_for_type(x509.DNSName))
            except Exception:
                pass
        return sans, None
    except (socket.gaierror, OSError, ssl.SSLError) as exc:
        return [], str(exc)


def check_cert_san(fqdn: str, port: int = 443, timeout: float = 5.0) -> dict:
    sans, err = _cert_sans(fqdn, port=port, timeout=timeout)
    if err:
        return {"fqdn": fqdn, "ok": False, "kind": "cert", "detail": f"handshake failed: {err}", "sans": []}
    if not sans:
        return {"fqdn": fqdn, "ok": False, "kind": "cert", "detail": "no DNS SANs", "sans": []}
    if san_covers(fqdn, sans):
        return {"fqdn": fqdn, "ok": True, "kind": "cert", "detail": f"SAN match", "sans": sans}
    return {
        "fqdn": fqdn,
        "ok": False,
        "kind": "cert",
        "detail": f"SAN list {sans} does not cover {fqdn!r}",
        "sans": sans,
    }


def san_covers(fqdn: str, sans: list[str]) -> bool:
    """RFC 6125 — exact match OR single-label wildcard match."""
    fqdn = fqdn.lower()
    for san in sans:
        san_l = san.lower()
        if san_l == fqdn:
            return True
        if san_l.startswith("*.") and fqdn.endswith(san_l[1:]) and fqdn.count(".") == san_l.count("."):
            return True
    return False


def run_checks(services: list[str], *, expected_ips: list[str] | None = None) -> list[dict]:
    results: list[dict] = []
    for slug in services:
        fqdn = _service_public_fqdn(slug)
        if not fqdn:
            results.append(
                {"service": slug, "ok": True, "skipped": True, "detail": "no public subdomain in catalog"}
            )
            continue
        dns = check_dns(fqdn, expected_ips=expected_ips)
        cert = check_cert_san(fqdn) if dns["ok"] else {"fqdn": fqdn, "ok": False, "kind": "cert", "detail": "skipped (DNS failed)"}
        results.append({"service": slug, "fqdn": fqdn, "dns": dns, "cert": cert, "ok": dns["ok"] and cert["ok"]})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--expected-ip", action="append", default=[], help="Expected resolved IPv4 (repeatable).")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args(argv)

    if args.all:
        services = _list_services()
    elif args.service:
        services = list(args.service)
    else:
        parser.print_usage(sys.stderr)
        print("preconverge_live_check: pass --service <slug> or --all.", file=sys.stderr)
        return 2

    if not services:
        print("preconverge_live_check: no services to check.", file=sys.stderr)
        return 2

    results = run_checks(services, expected_ips=args.expected_ip or None)
    if args.json_out:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for r in results:
            if r.get("skipped"):
                continue
            marker = "[ok] " if r["ok"] else "[FAIL]"
            print(f"{marker} {r['service']:<28} dns={r['dns']['detail']} cert={r['cert']['detail']}")
        ok = sum(1 for r in results if r["ok"])
        total = sum(1 for r in results if not r.get("skipped"))
        print(f"\npreconverge_live_check: {ok}/{total} services OK")

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
