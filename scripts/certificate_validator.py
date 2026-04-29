#!/usr/bin/env python3
"""
Certificate Validator — Check all edge-published domains for SSL validity.

Source of truth: config/certificate-catalog.json (ADR 0101)
Falls back to:   config/subdomain-catalog.json  (for domains not yet in catalog)

Usage:
  python3 scripts/certificate_validator.py [--check-all] [--json] [--fqdn FQDN]
  python3 scripts/certificate_validator.py --config config/certificate-catalog.json

Exit codes:
  0 = All certificates valid
  1 = One or more critical certificate issues found (expired or mismatch)
  2 = Script error
"""

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from typing import Optional


class CertStatus(Enum):
    VALID = "valid"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
    CERT_MISMATCH = "cert_mismatch"
    CONNECTION_FAILED = "connection_failed"
    UNKNOWN = "unknown"


@dataclass
class CertValidationResult:
    fqdn: str
    target: str
    target_port: int
    status: CertStatus
    common_name: Optional[str] = None
    subject_alt_names: Optional[list] = field(default_factory=list)
    not_after: Optional[str] = None
    days_until_expiry: Optional[int] = None
    error_message: Optional[str] = None
    service_id: Optional[str] = None


REPO_ROOT = Path(__file__).resolve().parent.parent


def detect_common_repo_root(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return repo_root
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (repo_root / common_dir).resolve()
    if common_dir.name == ".git":
        return common_dir.parent
    return repo_root


def discover_local_root(repo_root: Path, common_repo_root: Path | None = None) -> Path:
    shared_repo_root = common_repo_root or detect_common_repo_root(repo_root)
    direct_root = repo_root / ".local"
    shared_root = shared_repo_root / ".local"
    if shared_repo_root != repo_root and shared_root.exists():
        return shared_root
    if direct_root.exists():
        return direct_root
    if shared_root.exists():
        return shared_root
    if repo_root.parent.name == ".worktrees":
        sibling_root = repo_root.parent.parent / ".local"
        if sibling_root.exists():
            return sibling_root
    return direct_root


COMMON_REPO_ROOT = detect_common_repo_root(REPO_ROOT)
LOCAL_ROOT = discover_local_root(REPO_ROOT, COMMON_REPO_ROOT)


def _parse_der_cert(der_bytes: bytes) -> dict:
    """Parse a DER-encoded certificate into a dict compatible with getpeercert()."""
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_der_x509_certificate(der_bytes, default_backend())
        # Build a dict in the same format as ssl.getpeercert()
        result: dict = {}
        # subject CN
        cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        result["subject"] = tuple((("commonName", a.value),) for a in cn_attrs)
        # SANs
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = []
            for dns in san_ext.value.get_values_for_type(x509.DNSName):
                sans.append(("DNS", dns))
            for ip in san_ext.value.get_values_for_type(x509.IPAddress):
                sans.append(("IP Address", str(ip)))
            result["subjectAltName"] = tuple(sans)
        except x509.extensions.ExtensionNotFound:
            pass
        # dates
        result["notBefore"] = cert.not_valid_before_utc.strftime("%b %d %H:%M:%S %Y GMT")
        result["notAfter"] = cert.not_valid_after_utc.strftime("%b %d %H:%M:%S %Y GMT")
        return result
    except Exception:
        return {}


def get_certificate(fqdn: str, target: str, port: int, timeout: int = 10):
    """Connect to target:port, verify against fqdn, return (cert_dict, error)."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((target, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=fqdn) as ssock:
                return ssock.getpeercert(), None
    except ssl.SSLCertVerificationError as e:
        # Cert exists but CA is untrusted (e.g. internal step-ca). Retrieve raw DER.
        ctx2 = ssl.create_default_context()
        ctx2.check_hostname = False
        ctx2.verify_mode = ssl.CERT_NONE
        try:
            with socket.create_connection((target, port), timeout=timeout) as sock:
                with ctx2.wrap_socket(sock, server_hostname=fqdn) as ssock:
                    der = ssock.getpeercert(binary_form=True)
                    return _parse_der_cert(der) if der else {}, str(e)
        except Exception as e2:
            return None, str(e2)
    except Exception as e:
        return None, str(e)


def domain_in_cert(fqdn: str, cn: str, sans: list) -> bool:
    for pattern in [cn] + sans:
        if pattern == fqdn:
            return True
        if pattern.startswith("*.") and fqdn.endswith(pattern[2:]) and fqdn.count(".") == pattern.count("."):
            return True
    return False


def validate(
    fqdn: str, target: str, port: int, service_id: str, warn_days: float = 21, timeout: int = 10
) -> CertValidationResult:
    r = CertValidationResult(
        fqdn=fqdn, target=target, target_port=port, status=CertStatus.UNKNOWN, service_id=service_id
    )

    cert, error = get_certificate(fqdn, target, port, timeout)
    if not cert:
        r.status = CertStatus.CONNECTION_FAILED
        r.error_message = error
        return r

    cn = next((v for rdn in cert.get("subject", ()) for k, v in rdn if k == "commonName"), "")
    sans = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
    r.common_name = cn
    r.subject_alt_names = sans
    r.not_after = cert.get("notAfter", "")

    if not domain_in_cert(fqdn, cn, sans):
        r.status = CertStatus.CERT_MISMATCH
        r.error_message = f"CN={cn!r} SANs={sans} do not cover {fqdn!r}"
        return r

    try:
        expiry = datetime.strptime(r.not_after, "%b %d %H:%M:%S %Y %Z")
        delta = expiry - datetime.now(UTC).replace(tzinfo=None)
        days_float = delta.total_seconds() / 86400
        days = int(delta.days)
        r.days_until_expiry = days
        if days_float < 0:
            r.status = CertStatus.EXPIRED
            r.error_message = f"Expired {abs(days)} days ago"
        elif days_float < warn_days:
            r.status = CertStatus.EXPIRING_SOON
            r.error_message = f"Expires in {days} days"
        else:
            r.status = CertStatus.VALID
    except Exception as e:
        r.status = CertStatus.UNKNOWN
        r.error_message = f"Could not parse expiry: {e}"

    return r


def load_catalog(path: str) -> list:
    """Load config/certificate-catalog.json (ADR 0101 canonical source)."""
    try:
        with open(path) as f:
            data = json.load(f)
        entries = []
        for cert in data.get("certificates", []):
            ep = cert.get("endpoint", {})
            if not ep.get("host") or not ep.get("port"):
                continue
            policy = cert.get("policy", {})
            if "warn_hours" in policy and "warn_days" not in policy:
                warn_days = policy["warn_hours"] / 24
            else:
                warn_days = policy.get("warn_days", 21)
            entries.append(
                {
                    "fqdn": ep.get("server_name", ep["host"]),
                    "target": ep["host"],
                    "target_port": ep["port"],
                    "service_id": cert.get("service_id", ""),
                    "warn_days": warn_days,
                    "status": cert.get("status", "active"),
                }
            )
        return [e for e in entries if e["status"] == "active"]
    except FileNotFoundError:
        return []


def load_subdomain_catalog(path: str) -> list:
    """Fallback: load config/subdomain-catalog.json edge-published entries."""
    try:
        with open(path) as f:
            data = json.load(f)
        entries = []
        for sub in data.get("subdomains", []):
            if sub.get("exposure") not in ("edge-published", "edge-static"):
                continue
            if not sub.get("target"):
                continue
            entries.append(
                {
                    "fqdn": sub["fqdn"],
                    "target": sub["target"],
                    "target_port": sub.get("target_port", 443),
                    "service_id": sub.get("service_id", ""),
                    "warn_days": 21,
                    "status": "active",
                }
            )
        return entries
    except FileNotFoundError:
        return []


def format_text(results: list) -> str:
    lines = ["\n" + "=" * 72, "SSL CERTIFICATE VALIDATION REPORT", "=" * 72 + "\n"]
    by_status = {}
    for r in results:
        by_status.setdefault(r.status.value, []).append(r)

    lines += [
        f"Total Domains : {len(results)}",
        f"  Valid       : {len(by_status.get('valid', []))}",
        f"  Expiring    : {len(by_status.get('expiring_soon', []))}",
        f"  Expired     : {len(by_status.get('expired', []))}",
        f"  Mismatch    : {len(by_status.get('cert_mismatch', []))}",
        f"  Conn failed : {len(by_status.get('connection_failed', []))}",
        "",
    ]

    issues = [r for r in results if r.status not in (CertStatus.VALID,)]
    if issues:
        lines.append("ISSUES:")
        lines.append("-" * 72)
        for r in issues:
            lines.append(f"\n[{r.status.value.upper()}] {r.fqdn} ({r.service_id})")
            lines.append(f"  Target : {r.target}:{r.target_port}")
            if r.days_until_expiry is not None:
                lines.append(f"  Expires: {r.not_after} ({r.days_until_expiry}d)")
            if r.error_message:
                lines.append(f"  Error  : {r.error_message}")
            if r.status in (CertStatus.CERT_MISMATCH, CertStatus.EXPIRED, CertStatus.EXPIRING_SOON):
                lines.append("  Fix    : make configure-edge-publication env=production")
    else:
        lines.append("All certificates are valid.")

    lines.append("\n" + "=" * 72 + "\n")
    return "\n".join(lines)


def _read_platform_domain(path: Path) -> Optional[str]:
    try:
        import yaml
    except ImportError:
        return None
    if not path.is_file():
        return None
    try:
        identity = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    domain = str(identity.get("platform_domain", "")).strip()
    return domain or None


def _get_real_domain(deployment_slug: Optional[str] = None) -> Optional[str]:
    """Read platform_domain from the active deployment overlay (ADR 0456).

    Resolution order:
      1. If `deployment_slug` is provided, read from
         `.local/deployments/<slug>/identity.yml`.
      2. Otherwise, read the legacy single-deployment file
         `.local/identity.yml` (ADR 0410 Phase 4a).

    Returns None when the file is absent, malformed, or set to the
    generic placeholder `example.com`.
    """
    if deployment_slug:
        slug_path = LOCAL_ROOT / "deployments" / deployment_slug / "identity.yml"
        domain = _read_platform_domain(slug_path)
        if domain and domain != "example.com":
            return domain
        return None
    domain = _read_platform_domain(LOCAL_ROOT / "identity.yml")
    if domain and domain != "example.com":
        return domain
    return None


def _resolve_deployment_slug(explicit: Optional[str]) -> Optional[str]:
    """Resolve the active deployment slug for the cert validator (ADR 0456).

    Precedence (matches scripts/deployment.py):
      1. explicit --deployment flag
      2. $DEPLOYMENT environment variable
      3. .local/active-deployment file at the shared repo root
      4. None (caller falls back to legacy .local/identity.yml)
    """
    if explicit:
        return explicit.strip() or None
    env_slug = os.environ.get("DEPLOYMENT", "").strip()
    if env_slug:
        return env_slug
    active_file = LOCAL_ROOT / "active-deployment"
    if active_file.is_file():
        slug = active_file.read_text().strip()
        if slug:
            return slug
    return None


def _get_committed_domain() -> Optional[str]:
    return _read_platform_domain(REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml")


def _rewrite_hostname_for_real_domain(value: str, *, source_domain: Optional[str], real_domain: str) -> str:
    if not value or not source_domain or source_domain == real_domain:
        return value
    if value == source_domain:
        return real_domain
    suffix = f".{source_domain}"
    if value.endswith(suffix):
        return f"{value[: -len(suffix)]}.{real_domain}"
    return value


def _rewrite_entries_for_real_domain(entries: list[dict], real_domain: str) -> list[dict]:
    source_domain = _get_committed_domain() or "example.com"
    rewritten = []
    for entry in entries:
        updated = dict(entry)
        for field in ("fqdn", "target"):
            value = updated.get(field)
            if isinstance(value, str):
                updated[field] = _rewrite_hostname_for_real_domain(
                    value,
                    source_domain=source_domain,
                    real_domain=real_domain,
                )
        rewritten.append(updated)
    return rewritten


def _entry_matches_domain(entry: dict, domain: str) -> bool:
    fqdn = entry.get("fqdn", "")
    return fqdn == domain or fqdn.endswith(f".{domain}")


def _list_deployment_slugs() -> list[str]:
    """ADR 0458 — every deployment registered under .local/deployments/."""
    deployments_dir = LOCAL_ROOT / "deployments"
    if not deployments_dir.is_dir():
        return []
    return sorted(p.name for p in deployments_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


def main():
    parser = argparse.ArgumentParser(description="Validate SSL certificates for platform domains (ADR 0375)")
    parser.add_argument(
        "--config",
        default="config/certificate-catalog.json",
        help="Certificate catalog (default: config/certificate-catalog.json, ADR 0101)",
    )
    parser.add_argument(
        "--subdomain-config", default="config/subdomain-catalog.json", help="Subdomain catalog fallback"
    )
    parser.add_argument("--check-all", action="store_true", help="Check all active entries (implied when no --fqdn)")
    parser.add_argument("--fqdn", help="Check only this FQDN")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Output results as JSON")
    parser.add_argument("--timeout", type=int, default=10, help="Connection timeout in seconds (default: 10)")
    parser.add_argument(
        "--deployment",
        help=(
            "Validate certs for this deployment slug only (ADR 0456). "
            "Reads .local/deployments/<slug>/identity.yml and only checks "
            "FQDNs that match. Defaults to $DEPLOYMENT or "
            ".local/active-deployment; falls back to legacy "
            ".local/identity.yml when no deployment is registered."
        ),
    )
    parser.add_argument(
        "--all-deployments",
        action="store_true",
        help=(
            "Validate certs for every deployment under .local/deployments/ "
            "in turn (ADR 0458). Aggregate results; exit 1 if any deployment "
            "reports an expired or mismatched cert."
        ),
    )
    args = parser.parse_args()

    entries_master = load_catalog(args.config)
    if not entries_master:
        print(f"[warn] {args.config} empty or missing — using {args.subdomain_config}", file=sys.stderr)
        entries_master = load_subdomain_catalog(args.subdomain_config)

    if not entries_master:
        print("No active domains found to validate.", file=sys.stderr)
        sys.exit(2)

    # ADR 0458 — multi-deployment dispatch. When --all-deployments is set
    # (or implicitly when no slug resolved AND multiple deployments exist),
    # iterate per slug and aggregate results. Single-deployment installs
    # are unaffected — they take the legacy fallback path below.
    if args.all_deployments or (not args.deployment and not args.fqdn and len(_list_deployment_slugs()) > 1):
        slugs = _list_deployment_slugs()
        if not slugs:
            print(
                "[info] --all-deployments: no .local/deployments/ — nothing to validate.",
                file=sys.stderr,
            )
            sys.exit(0)
        all_results: list = []
        for slug in slugs:
            print(f"=== Validating deployment={slug} ===", file=sys.stderr)
            slug_domain = _get_real_domain(deployment_slug=slug)
            if slug_domain is None:
                print(
                    f"[info] No real platform_domain for deployment={slug} — skipping.",
                    file=sys.stderr,
                )
                continue
            slug_entries = _rewrite_entries_for_real_domain(list(entries_master), slug_domain)
            slug_entries = [e for e in slug_entries if _entry_matches_domain(e, slug_domain)]
            if not slug_entries:
                print(
                    f"[info] No catalog entries match domain '{slug_domain}' for deployment={slug} — skipping.",
                    file=sys.stderr,
                )
                continue
            for e in slug_entries:
                print(f"Checking {e['fqdn']} (deployment={slug})...", file=sys.stderr)
                all_results.append(
                    validate(
                        fqdn=e["fqdn"],
                        target=e["target"],
                        port=e["target_port"],
                        service_id=e["service_id"],
                        warn_days=e.get("warn_days", 21),
                        timeout=args.timeout,
                    )
                )
        if args.json_out:
            print(
                json.dumps(
                    [
                        {
                            "fqdn": r.fqdn,
                            "service": r.service_id,
                            "status": r.status.value,
                            "cn": r.common_name,
                            "sans": r.subject_alt_names or [],
                            "expires": r.not_after,
                            "days_until_expiry": r.days_until_expiry,
                            "error": r.error_message,
                        }
                        for r in all_results
                    ],
                    indent=2,
                )
            )
        else:
            print(format_text(all_results))
        sys.exit(1 if any(r.status in (CertStatus.EXPIRED, CertStatus.CERT_MISMATCH) for r in all_results) else 0)

    entries = list(entries_master)
    deployment_slug = _resolve_deployment_slug(args.deployment)
    real_domain = _get_real_domain(deployment_slug=deployment_slug)
    if real_domain:
        entries = _rewrite_entries_for_real_domain(entries, real_domain)

    # ADR 0410 Phase 4a: skip example.com (generic committed placeholder).
    # ADR 0456: when a deployment is resolved, only check that deployment's
    # domains. Cross-deployment drift becomes a non-event for the active
    # deployment's gate because the validator only inspects domains owned by it.
    if not args.fqdn:
        if real_domain is None:
            slug_hint = f" (deployment={deployment_slug})" if deployment_slug else ""
            source_hint = (
                f".local/deployments/{deployment_slug}/identity.yml" if deployment_slug else ".local/identity.yml"
            )
            print(
                f"[info] No real platform_domain in {source_hint}{slug_hint} — skipping TLS validation "
                "(committed catalog uses example.com placeholder). Configure the local overlay "
                "with your real domain to enable certificate checks.",
                file=sys.stderr,
            )
            sys.exit(0)
        entries = [e for e in entries if _entry_matches_domain(e, real_domain)]
        if not entries:
            slug_hint = f" (deployment={deployment_slug})" if deployment_slug else ""
            print(
                f"[info] No catalog entries match configured domain '{real_domain}'{slug_hint} — skipping.",
                file=sys.stderr,
            )
            sys.exit(0)

    if args.fqdn:
        entries = [e for e in entries if e["fqdn"] == args.fqdn]
        if not entries:
            print(f"FQDN {args.fqdn!r} not in catalog.", file=sys.stderr)
            sys.exit(2)

    results = []
    for e in entries:
        print(f"Checking {e['fqdn']}...", file=sys.stderr)
        results.append(
            validate(
                fqdn=e["fqdn"],
                target=e["target"],
                port=e["target_port"],
                service_id=e["service_id"],
                warn_days=e.get("warn_days", 21),
                timeout=args.timeout,
            )
        )

    if args.json_out:
        print(
            json.dumps(
                [
                    {
                        "fqdn": r.fqdn,
                        "service": r.service_id,
                        "status": r.status.value,
                        "cn": r.common_name,
                        "sans": r.subject_alt_names or [],
                        "expires": r.not_after,
                        "days_until_expiry": r.days_until_expiry,
                        "error": r.error_message,
                    }
                    for r in results
                ],
                indent=2,
            )
        )
    else:
        print(format_text(results))

    sys.exit(1 if any(r.status in (CertStatus.EXPIRED, CertStatus.CERT_MISMATCH) for r in results) else 0)


if __name__ == "__main__":
    main()
