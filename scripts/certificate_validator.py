#!/usr/bin/env python3
"""
Certificate Validator — Check all domains in subdomain-catalog.json for SSL validity.

Purpose:
  - Validate certificates for all published subdomains
  - Check expiration dates
  - Verify certificate matches domain name
  - Report issues and remediation steps

Usage:
  python3 scripts/certificate_validator.py [--check-all] [--json] [--fix] [--config config/subdomain-catalog.json]

Exit codes:
  0 = All certificates valid
  1 = One or more certificate issues found
  2 = Script error
"""

import json
import sys
import ssl
import socket
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import subprocess
from dataclasses import dataclass
from enum import Enum


class CertStatus(Enum):
    """Certificate validation status."""
    VALID = "valid"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
    CERT_MISMATCH = "cert_mismatch"
    CONNECTION_FAILED = "connection_failed"
    UNKNOWN = "unknown"


@dataclass
class CertValidationResult:
    """Result of a single certificate validation."""
    fqdn: str
    target: str
    target_port: int
    status: CertStatus
    common_name: Optional[str] = None
    subject_alt_names: Optional[List[str]] = None
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    days_until_expiry: Optional[int] = None
    error_message: Optional[str] = None
    service_id: Optional[str] = None


def get_certificate_info(fqdn: str, target: str, port: int, timeout: int = 10) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Retrieve certificate information for a given FQDN.

    Returns:
      (cert_dict, error_message)
    """
    try:
        # Create SSL context
        context = ssl.create_default_context()

        # Connect and get certificate
        with socket.create_connection((target, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=fqdn) as ssock:
                cert_der = ssock.getpeercert(binary_form=False)
                return cert_der, None
    except socket.timeout:
        return None, f"Timeout connecting to {target}:{port}"
    except ssl.SSLCertVerificationError as e:
        # Still try to get the cert info even if verification fails
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with socket.create_connection((target, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=fqdn) as ssock:
                    cert_der = ssock.getpeercert(binary_form=False)
                    return cert_der, str(e)
        except Exception as fallback_error:
            return None, str(fallback_error)
    except Exception as e:
        return None, str(e)


def extract_cert_info(cert: Dict) -> Tuple[str, List[str]]:
    """Extract common name and SANs from certificate."""
    cn = ""
    sans = []

    # Get common name
    for rdn in cert.get("subject", ()):
        for name_type, value in rdn:
            if name_type == "commonName":
                cn = value
                break

    # Get SubjectAltName
    for key, value in cert.get("subjectAltName", []):
        if key == "DNS":
            sans.append(value)

    return cn, sans


def domain_matches_cert(fqdn: str, common_name: str, san_list: List[str]) -> bool:
    """Check if domain matches certificate CN or SANs."""
    # Direct match
    if fqdn == common_name or fqdn in san_list:
        return True

    # Wildcard match
    for pattern in [common_name] + san_list:
        if pattern.startswith("*."):
            domain_suffix = pattern[2:]  # Remove "*."
            if fqdn.endswith(domain_suffix):
                return True

    return False


def validate_certificate(fqdn: str, target: str, target_port: int, service_id: str = "") -> CertValidationResult:
    """Validate a single certificate."""
    result = CertValidationResult(
        fqdn=fqdn,
        target=target,
        target_port=target_port,
        status=CertStatus.UNKNOWN,
        service_id=service_id
    )

    cert, error = get_certificate_info(fqdn, target, target_port)

    if not cert:
        result.status = CertStatus.CONNECTION_FAILED
        result.error_message = error
        return result

    # Extract certificate info
    cn, sans = extract_cert_info(cert)
    result.common_name = cn
    result.subject_alt_names = sans
    result.not_before = cert.get("notBefore", "unknown")
    result.not_after = cert.get("notAfter", "unknown")

    # Check if domain matches certificate
    if not domain_matches_cert(fqdn, cn, sans):
        result.status = CertStatus.CERT_MISMATCH
        result.error_message = f"Certificate CN={cn}, SANs={sans}, but domain is {fqdn}"
        return result

    # Check expiration
    try:
        expiry_date = datetime.strptime(cert.get("notAfter", ""), "%b %d %H:%M:%S %Y %Z")
        now = datetime.utcnow()
        days_until = (expiry_date - now).days
        result.days_until_expiry = days_until

        if days_until < 0:
            result.status = CertStatus.EXPIRED
            result.error_message = f"Certificate expired {abs(days_until)} days ago"
        elif days_until < 30:
            result.status = CertStatus.EXPIRING_SOON
            result.error_message = f"Certificate expires in {days_until} days"
        else:
            result.status = CertStatus.VALID
    except Exception as e:
        result.status = CertStatus.UNKNOWN
        result.error_message = f"Could not parse expiration date: {e}"

    return result


def load_subdomain_catalog(config_path: str) -> List[Dict]:
    """Load subdomain catalog from JSON."""
    try:
        with open(config_path, 'r') as f:
            catalog = json.load(f)
        return catalog.get("subdomains", [])
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(2)


def format_results(results: List[CertValidationResult], json_output: bool = False) -> str:
    """Format validation results for output."""
    if json_output:
        return json.dumps([{
            "fqdn": r.fqdn,
            "service": r.service_id,
            "status": r.status.value,
            "cn": r.common_name,
            "sans": r.subject_alt_names or [],
            "expires": r.not_after,
            "days_until_expiry": r.days_until_expiry,
            "error": r.error_message
        } for r in results], indent=2)

    output = []
    output.append("\n" + "=" * 80)
    output.append("SSL CERTIFICATE VALIDATION REPORT")
    output.append("=" * 80 + "\n")

    # Group by status
    by_status = {}
    for r in results:
        status = r.status.value
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(r)

    # Summary
    total = len(results)
    valid = len(by_status.get("valid", []))
    expiring_soon = len(by_status.get("expiring_soon", []))
    expired = len(by_status.get("expired", []))
    mismatch = len(by_status.get("cert_mismatch", []))
    failed = len(by_status.get("connection_failed", []))

    output.append(f"Total Domains: {total}")
    output.append(f"✓ Valid: {valid}")
    output.append(f"⚠ Expiring Soon (< 30 days): {expiring_soon}")
    output.append(f"✗ Expired: {expired}")
    output.append(f"✗ Certificate Mismatch: {mismatch}")
    output.append(f"✗ Connection Failed: {failed}")
    output.append("")

    # Issues
    issues = []
    for status in ["expired", "cert_mismatch", "connection_failed", "expiring_soon"]:
        for r in by_status.get(status, []):
            issues.append(r)

    if issues:
        output.append("ISSUES FOUND:")
        output.append("-" * 80)
        for r in issues:
            output.append(f"\n[{r.status.value.upper()}] {r.fqdn} ({r.service_id})")
            output.append(f"  Target: {r.target}:{r.target_port}")
            output.append(f"  CN: {r.common_name}")
            output.append(f"  SANs: {', '.join(r.subject_alt_names or [])}")
            if r.days_until_expiry is not None:
                output.append(f"  Expires: {r.not_after} ({r.days_until_expiry} days)")
            if r.error_message:
                output.append(f"  Error: {r.error_message}")

            # Remediation steps
            if r.status == CertStatus.CERT_MISMATCH:
                output.append(f"\n  REMEDIATION:")
                output.append(f"  - The certificate for {r.fqdn} does not match.")
                output.append(f"  - Check that all subdomains are included in the certificate request.")
                output.append(f"  - Run: make converge-nginx-edge env=production")
                output.append(f"  - Check certbot renewal process for edge-published domains.")
            elif r.status == CertStatus.EXPIRING_SOON:
                output.append(f"\n  REMEDIATION:")
                output.append(f"  - Certificate expires in {r.days_until_expiry} days")
                output.append(f"  - Run: make converge-nginx-edge env=production")
                output.append(f"  - Or manually: sudo certbot renew --cert-name {r.common_name}")
            elif r.status == CertStatus.EXPIRED:
                output.append(f"\n  REMEDIATION:")
                output.append(f"  - CRITICAL: Certificate is expired!")
                output.append(f"  - Run immediately: make converge-nginx-edge env=production")
                output.append(f"  - Or: sudo certbot renew --force-renewal --cert-name {r.common_name}")
            elif r.status == CertStatus.CONNECTION_FAILED:
                output.append(f"\n  REMEDIATION:")
                output.append(f"  - Could not connect to {r.target}:{r.target_port}")
                output.append(f"  - Error: {r.error_message}")
                output.append(f"  - Check if the host/port is correct and accessible.")

    output.append("\n" + "=" * 80 + "\n")
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Validate SSL certificates for all platform domains")
    parser.add_argument("--config", default="config/subdomain-catalog.json",
                        help="Path to subdomain catalog config")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--check-all", action="store_true",
                        help="Check all domains, not just edge-published")
    parser.add_argument("--fqdn", help="Check only a specific FQDN")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Connection timeout in seconds")

    args = parser.parse_args()

    # Load catalog
    catalog = load_subdomain_catalog(args.config)

    # Filter domains
    domains_to_check = []
    for entry in catalog:
        if args.fqdn and entry["fqdn"] != args.fqdn:
            continue
        if not args.check_all and entry.get("exposure") not in ["edge-published", "edge-static"]:
            continue
        domains_to_check.append(entry)

    if not domains_to_check:
        print("No domains to check", file=sys.stderr)
        sys.exit(0)

    # Validate certificates
    results = []
    for entry in domains_to_check:
        print(f"Checking {entry['fqdn']}...", file=sys.stderr)
        result = validate_certificate(
            fqdn=entry["fqdn"],
            target=entry["target"],
            target_port=entry.get("target_port", 443),
            service_id=entry.get("service_id", "")
        )
        results.append(result)

    # Output results
    output = format_results(results, json_output=args.json)
    print(output)

    # Exit code
    has_issues = any(r.status in [
        CertStatus.EXPIRED,
        CertStatus.CERT_MISMATCH,
        CertStatus.CONNECTION_FAILED
    ] for r in results)

    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
