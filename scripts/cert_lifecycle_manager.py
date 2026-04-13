#!/usr/bin/env python3
"""
Cert Lifecycle Manager — ADR 0414

Programmatic entry point for certificate and subdomain lifecycle operations
on the platform nginx edge. Usable from the shell, cron, and LibreChat agent.

Commands:
  list              List all subdomains with cert status
  create-subdomain  Add subdomain to catalogs + issue cert + deploy nginx config
  delete-subdomain  Remove subdomain from catalogs + clean cert + nginx config
  renew             Force-renew cert for a domain (or all domains)
  revoke            Revoke cert and remove from catalogs
  sync-missing      Detect and repair subdomains with cert_mismatch or no cert
  status            JSON status for a specific FQDN

Usage:
  python3 scripts/cert_lifecycle_manager.py list [--json]
  python3 scripts/cert_lifecycle_manager.py create-subdomain \\
      --domain new.example.com --target 10.10.10.92 --target-port 3000 [--apply]
  python3 scripts/cert_lifecycle_manager.py delete-subdomain \\
      --domain old.example.com [--apply]
  python3 scripts/cert_lifecycle_manager.py renew [--domain FQDN] [--apply]
  python3 scripts/cert_lifecycle_manager.py revoke --domain FQDN [--apply]
  python3 scripts/cert_lifecycle_manager.py sync-missing [--apply] [--json]
  python3 scripts/cert_lifecycle_manager.py status --domain FQDN [--json]

Flags:
  --apply               Actually make changes (default: dry-run)
  --domain FQDN         Target a specific domain
  --target HOST         Target host/IP for new subdomain
  --target-port PORT    Target port for new subdomain (default: 443)
  --service-id ID       Service ID for catalog entry (default: derived from domain)
  --skip-cert-validation  Skip TLS validation step (for forks without DNS API)
  --json                JSON output for agent tooling
  --no-nginx-reload     Skip nginx reload after cert change
  --env ENV             Ansible environment (default: production)

Exit codes:
  0  Success (or dry-run completed)
  1  One or more operations failed
  2  Script error (bad args, missing files)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBDOMAIN_CATALOG = REPO_ROOT / "config" / "subdomain-catalog.json"
CERT_CATALOG = REPO_ROOT / "config" / "certificate-catalog.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_common_repo_root(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        common_dir = Path(result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (repo_root / common_dir).resolve()
        if common_dir.name == ".git":
            return common_dir.parent
    except Exception:
        pass
    return repo_root


def _discover_local_root(repo_root: Path) -> Path:
    common = _detect_common_repo_root(repo_root)
    for candidate in [common / ".local", repo_root / ".local"]:
        if candidate.exists():
            return candidate
    if repo_root.parent.name == ".worktrees":
        sibling = repo_root.parent.parent / ".local"
        if sibling.exists():
            return sibling
    return repo_root / ".local"


LOCAL_ROOT = _discover_local_root(REPO_ROOT)


def _read_identity() -> dict:
    path = LOCAL_ROOT / "identity.yml"
    if not path.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def _get_platform_domain() -> str:
    identity = _read_identity()
    domain = str(identity.get("platform_domain", "")).strip()
    return domain if domain and domain != "example.com" else "example.com"


def _get_cert_validation_mode() -> str:
    """Return enforce|warn|skip from .local/identity.yml (ADR 0414)."""
    identity = _read_identity()
    mode = str(identity.get("platform_cert_validation_mode", "enforce")).strip()
    return mode if mode in ("enforce", "warn", "skip") else "enforce"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"[error] Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _out(obj, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(obj, indent=2))
    else:
        if isinstance(obj, dict) and "message" in obj:
            prefix = "[ok]" if obj.get("ok") else "[error]"
            print(f"{prefix} {obj['message']}")
        elif isinstance(obj, list):
            for item in obj:
                print(json.dumps(item, indent=2))
        else:
            print(json.dumps(obj, indent=2))


def _run_cert_validator(args_extra: list = None) -> list:
    """Run certificate_validator.py --check-all --json, return parsed results."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "certificate_validator.py"),
        "--check-all",
        "--json",
    ]
    if args_extra:
        cmd.extend(args_extra)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
    return []


def _run_ansible(playbook: str, env: str, extra_vars: dict = None, dry_run: bool = True) -> int:
    """Run an ansible-playbook command. Returns exit code."""
    cmd = ["ansible-playbook", playbook, f"-e env={env}"]
    if extra_vars:
        cmd += ["-e", json.dumps(extra_vars)]
    if dry_run:
        cmd += ["--check", "--diff"]
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode


def _run_make(target: str, env: str, dry_run: bool = True) -> int:
    """Run a make target. Returns exit code."""
    cmd = ["make", target, f"env={env}"]
    if dry_run:
        print(f"[dry-run] Would run: {' '.join(cmd)}", file=sys.stderr)
        return 0
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args) -> int:
    """List all subdomains with their cert status."""
    sub_data = _load_json(SUBDOMAIN_CATALOG)
    subdomains = sub_data.get("subdomains", [])

    if not subdomains:
        _out({"ok": False, "message": "No subdomains found in catalog"}, args.json)
        return 1

    validation_mode = _get_cert_validation_mode()
    if not args.skip_cert_validation and validation_mode != "skip":
        cert_results = _run_cert_validator()
        cert_map = {r["fqdn"]: r for r in cert_results}
    else:
        cert_map = {}

    rows = []
    for sub in subdomains:
        fqdn = sub.get("fqdn", "")
        exposure = sub.get("exposure", "internal")
        status = sub.get("status", "active")
        cert_info = cert_map.get(fqdn, {})
        rows.append(
            {
                "fqdn": fqdn,
                "exposure": exposure,
                "status": status,
                "target": sub.get("target", ""),
                "target_port": sub.get("target_port", 443),
                "service_id": sub.get("service_id", ""),
                "cert_status": cert_info.get("status", "not_checked"),
                "cert_expires": cert_info.get("expires"),
                "cert_days_until_expiry": cert_info.get("days_until_expiry"),
                "cert_error": cert_info.get("error"),
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'FQDN':<45} {'EXPOSURE':<16} {'CERT_STATUS':<16} {'EXPIRES_IN'}")
        print("-" * 100)
        for row in rows:
            days = row["cert_days_until_expiry"]
            expires = f"{days}d" if days is not None else "-"
            print(f"{row['fqdn']:<45} {row['exposure']:<16} {row['cert_status']:<16} {expires}")

    mismatches = [r for r in rows if r["cert_status"] == "cert_mismatch"]
    if mismatches:
        if not args.json:
            print(f"\n[warn] {len(mismatches)} cert_mismatch entries. Run:")
            print("  python3 scripts/cert_lifecycle_manager.py sync-missing --apply")
    return 0


def cmd_create_subdomain(args) -> int:
    """Add a new subdomain to catalogs and issue cert + nginx config."""
    domain = args.domain
    target = args.target
    port = args.target_port
    service_id = args.service_id or domain.split(".")[0]
    env = args.env

    if not domain or not target:
        print("[error] --domain and --target are required", file=sys.stderr)
        return 2

    platform_domain = _get_platform_domain()
    if not domain.endswith(f".{platform_domain}") and domain != platform_domain:
        print(
            f"[warn] Domain {domain!r} does not match platform domain {platform_domain!r}",
            file=sys.stderr,
        )

    # Check if already exists
    sub_data = _load_json(SUBDOMAIN_CATALOG)
    existing = [s for s in sub_data.get("subdomains", []) if s.get("fqdn") == domain]
    if existing:
        _out({"ok": False, "message": f"{domain} already exists in subdomain-catalog.json"}, args.json)
        return 1

    new_sub = {
        "prefix": domain.split(".")[0],
        "fqdn": domain,
        "exposure": "edge-published",
        "target": target,
        "target_port": port,
        "service_id": service_id,
        "status": "active",
        "added_by": "cert_lifecycle_manager",
        "added_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    new_cert = {
        "service_id": service_id,
        "status": "active",
        "endpoint": {
            "host": target,
            "port": 443,
            "server_name": domain,
        },
        "policy": {
            "warn_days": 21,
        },
        "added_by": "cert_lifecycle_manager",
        "added_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    if args.dry_run:
        _out(
            {
                "ok": True,
                "dry_run": True,
                "message": f"Would create subdomain {domain} → {target}:{port}",
                "subdomain_entry": new_sub,
                "cert_catalog_entry": new_cert,
                "next_steps": [
                    f"Add to config/subdomain-catalog.json",
                    f"Add to config/certificate-catalog.json",
                    f"Run: make converge-nginx-edge env={env}",
                    f"Verify: python3 scripts/certificate_validator.py --fqdn {domain}",
                ],
            },
            args.json,
        )
        return 0

    # Apply: update catalogs
    sub_data.setdefault("subdomains", []).append(new_sub)
    _save_json(SUBDOMAIN_CATALOG, sub_data)

    cert_data = _load_json(CERT_CATALOG)
    cert_data.setdefault("certificates", []).append(new_cert)
    _save_json(CERT_CATALOG, cert_data)

    print(f"[ok] Added {domain} to subdomain-catalog.json and certificate-catalog.json", file=sys.stderr)

    # Deploy nginx edge
    rc = _run_make("converge-nginx-edge", env=env, dry_run=False)
    if rc != 0:
        _out(
            {
                "ok": False,
                "message": f"certbot/nginx converge failed (exit {rc}). Catalog entries written. Run manually: make converge-nginx-edge env={env}",
            },
            args.json,
        )
        return 1

    # Verify cert
    if not args.skip_cert_validation and _get_cert_validation_mode() != "skip":
        results = _run_cert_validator(["--fqdn", domain])
        cert_ok = results and results[0].get("status") == "valid"
        _out(
            {
                "ok": cert_ok,
                "message": f"Created {domain}. Cert status: {results[0].get('status') if results else 'unknown'}",
                "cert": results[0] if results else None,
            },
            args.json,
        )
        return 0 if cert_ok else 1

    _out({"ok": True, "message": f"Created {domain} → {target}:{port}. Cert validation skipped."}, args.json)
    return 0


def cmd_delete_subdomain(args) -> int:
    """Remove a subdomain from catalogs and clean cert + nginx config."""
    domain = args.domain
    env = args.env

    if not domain:
        print("[error] --domain is required", file=sys.stderr)
        return 2

    sub_data = _load_json(SUBDOMAIN_CATALOG)
    before = sub_data.get("subdomains", [])
    after = [s for s in before if s.get("fqdn") != domain]

    if len(before) == len(after):
        _out({"ok": False, "message": f"{domain} not found in subdomain-catalog.json"}, args.json)
        return 1

    removed_sub = next(s for s in before if s.get("fqdn") == domain)

    cert_data = _load_json(CERT_CATALOG)
    cert_before = cert_data.get("certificates", [])
    cert_after = [c for c in cert_before if c.get("endpoint", {}).get("server_name") != domain]

    if args.dry_run:
        _out(
            {
                "ok": True,
                "dry_run": True,
                "message": f"Would remove {domain} from catalogs",
                "removed_subdomain": removed_sub,
                "cert_entries_removed": len(cert_before) - len(cert_after),
                "next_steps": [
                    f"Remove from config/subdomain-catalog.json",
                    f"Remove from config/certificate-catalog.json",
                    f"Run: make converge-nginx-edge env={env}",
                    f"Note: cert SAN will be rebuilt without {domain}",
                ],
            },
            args.json,
        )
        return 0

    sub_data["subdomains"] = after
    _save_json(SUBDOMAIN_CATALOG, sub_data)

    cert_data["certificates"] = cert_after
    _save_json(CERT_CATALOG, cert_data)

    print(f"[ok] Removed {domain} from catalogs", file=sys.stderr)

    # Re-deploy nginx edge (will rebuild cert without this domain)
    rc = _run_make("converge-nginx-edge", env=env, dry_run=False)
    if rc != 0:
        _out(
            {
                "ok": False,
                "message": f"nginx converge after deletion failed (exit {rc}). Catalog entries removed. Run manually: make converge-nginx-edge env={env}",
            },
            args.json,
        )
        return 1

    _out({"ok": True, "message": f"Deleted subdomain {domain} and rebuilt nginx edge cert"}, args.json)
    return 0


def cmd_renew(args) -> int:
    """Force-renew cert for a domain or all domains."""
    env = args.env

    if args.domain:
        playbook = "playbooks/fix-edge-certificate.yml"
        extra_vars = {"target_fqdn": args.domain, "force_renewal": True}
    else:
        playbook = "playbooks/fix-edge-certificate.yml"
        extra_vars = {"force_renewal": True}

    if args.dry_run:
        domains_desc = args.domain or "all edge-published domains"
        _out(
            {
                "ok": True,
                "dry_run": True,
                "message": f"Would force-renew cert for {domains_desc}",
                "playbook": playbook,
                "extra_vars": extra_vars,
                "next_steps": [f"Re-run with --apply to execute"],
            },
            args.json,
        )
        return 0

    rc = _run_ansible(playbook, env=env, extra_vars=extra_vars, dry_run=False)
    if rc != 0:
        _out({"ok": False, "message": f"Cert renewal failed (exit {rc})"}, args.json)
        return 1

    # Verify after renewal
    if not args.skip_cert_validation and _get_cert_validation_mode() != "skip":
        if args.domain:
            results = _run_cert_validator(["--fqdn", args.domain])
        else:
            results = _run_cert_validator()
        mismatches = [r for r in results if r.get("status") in ("cert_mismatch", "expired")]
        _out(
            {
                "ok": len(mismatches) == 0,
                "message": f"Renewal complete. {len(mismatches)} remaining issues."
                if mismatches
                else "Renewal complete. All certs valid.",
                "remaining_issues": mismatches,
            },
            args.json,
        )
        return 0 if not mismatches else 1

    _out({"ok": True, "message": "Renewal triggered. Cert validation skipped."}, args.json)
    return 0


def cmd_revoke(args) -> int:
    """Revoke cert for a domain."""
    domain = args.domain
    if not domain:
        print("[error] --domain is required for revoke", file=sys.stderr)
        return 2

    if args.dry_run:
        _out(
            {
                "ok": True,
                "dry_run": True,
                "message": f"Would revoke cert for {domain}",
                "warning": "This will also trigger a full edge cert rebuild. Use delete-subdomain for clean removal.",
                "next_steps": [
                    f"certbot revoke --cert-name {domain}",
                    f"make converge-nginx-edge env={args.env}",
                ],
            },
            args.json,
        )
        return 0

    # Mark as inactive in cert catalog
    cert_data = _load_json(CERT_CATALOG)
    changed = False
    for cert in cert_data.get("certificates", []):
        if cert.get("endpoint", {}).get("server_name") == domain:
            cert["status"] = "revoked"
            cert["revoked_date"] = datetime.utcnow().strftime("%Y-%m-%d")
            changed = True

    if not changed:
        _out({"ok": False, "message": f"{domain} not found in certificate-catalog.json"}, args.json)
        return 1

    _save_json(CERT_CATALOG, cert_data)

    # Run certbot revoke on the edge host via playbook
    rc = _run_ansible(
        "playbooks/fix-edge-certificate.yml",
        env=args.env,
        extra_vars={"revoke_domain": domain},
        dry_run=False,
    )
    if rc != 0:
        _out(
            {
                "ok": False,
                "message": f"certbot revoke returned exit {rc}. Catalog marked revoked; manual certbot command may be needed.",
            },
            args.json,
        )
        return 1

    _out({"ok": True, "message": f"Revoked cert for {domain}"}, args.json)
    return 0


def cmd_sync_missing(args) -> int:
    """Detect subdomains with cert_mismatch or missing cert coverage; repair them.

    This is the cron-safe operation. It:
    1. Runs certificate_validator.py to find cert_mismatch / connection_failed entries
    2. Cross-references against subdomain-catalog.json
    3. Triggers make converge-nginx-edge to rebuild the shared SAN cert
    4. Re-validates and reports remaining issues
    """
    validation_mode = _get_cert_validation_mode()

    if args.skip_cert_validation or validation_mode == "skip":
        _out(
            {
                "ok": True,
                "message": "Cert validation skipped (SKIP_CERT_VALIDATION or platform_cert_validation_mode=skip)",
                "mode": validation_mode,
            },
            args.json,
        )
        return 0

    print("[sync-missing] scanning domains...", file=sys.stderr)
    before_results = _run_cert_validator()

    if not before_results:
        _out({"ok": True, "message": "No domains found in catalog or validator returned empty"}, args.json)
        return 0

    mismatches = [r for r in before_results if r.get("status") in ("cert_mismatch", "expired")]
    connection_failures = [r for r in before_results if r.get("status") == "connection_failed"]
    valid = [r for r in before_results if r.get("status") == "valid"]

    if not mismatches:
        _out(
            {
                "ok": True,
                "message": f"All {len(valid)} domains have valid certificates. No sync needed.",
                "summary": {
                    "total": len(before_results),
                    "valid": len(valid),
                    "connection_failed": len(connection_failures),
                    "mismatches": 0,
                },
            },
            args.json,
        )
        return 0

    print(
        f"[sync-missing] found {len(mismatches)} cert_mismatch/expired entries: "
        + ", ".join(r["fqdn"] for r in mismatches),
        file=sys.stderr,
    )

    if args.dry_run:
        _out(
            {
                "ok": True,
                "dry_run": True,
                "message": f"Would repair {len(mismatches)} domains via converge-nginx-edge",
                "mismatches": mismatches,
                "next_steps": ["Re-run with --apply to execute"],
            },
            args.json,
        )
        return 0

    # Apply: re-converge nginx edge (certbot will add missing SANs)
    rc = _run_make("converge-nginx-edge", env=args.env, dry_run=False)
    if rc != 0:
        _out(
            {
                "ok": False,
                "message": f"converge-nginx-edge failed (exit {rc}). {len(mismatches)} mismatches remain.",
                "mismatches": mismatches,
            },
            args.json,
        )
        return 1

    # Post-check
    after_results = _run_cert_validator()
    after_mismatches = [r for r in after_results if r.get("status") in ("cert_mismatch", "expired")]
    after_valid = [r for r in after_results if r.get("status") == "valid"]

    fixed = [r for r in mismatches if r["fqdn"] not in {a["fqdn"] for a in after_mismatches}]

    result = {
        "ok": len(after_mismatches) == 0,
        "message": (
            f"Sync complete. Fixed {len(fixed)}/{len(mismatches)} domains."
            if len(after_mismatches) == 0
            else f"Sync partial. {len(after_mismatches)} domains still broken."
        ),
        "summary": {
            "total": len(after_results),
            "valid": len(after_valid),
            "fixed": len(fixed),
            "remaining_mismatches": len(after_mismatches),
        },
        "fixed": [r["fqdn"] for r in fixed],
        "remaining_issues": after_mismatches,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    _out(result, args.json)

    # Write log file for cron audit trail
    log_dir = Path("/var/log")
    if log_dir.exists() and os.access(log_dir, os.W_OK):
        log_path = log_dir / f"cert-sync-{datetime.utcnow().strftime('%Y%m%d')}.json"
        try:
            log_path.write_text(json.dumps(result, indent=2) + "\n")
        except Exception:
            pass  # Non-fatal

    return 0 if result["ok"] else 1


def cmd_status(args) -> int:
    """JSON status for a specific FQDN."""
    domain = args.domain
    if not domain:
        print("[error] --domain is required for status", file=sys.stderr)
        return 2

    sub_data = _load_json(SUBDOMAIN_CATALOG)
    sub_entry = next(
        (s for s in sub_data.get("subdomains", []) if s.get("fqdn") == domain),
        None,
    )

    cert_data = _load_json(CERT_CATALOG)
    cert_entry = next(
        (c for c in cert_data.get("certificates", []) if c.get("endpoint", {}).get("server_name") == domain),
        None,
    )

    validation_mode = _get_cert_validation_mode()
    if not args.skip_cert_validation and validation_mode != "skip":
        results = _run_cert_validator(["--fqdn", domain])
        live_cert = results[0] if results else None
    else:
        live_cert = None

    _out(
        {
            "fqdn": domain,
            "in_subdomain_catalog": sub_entry is not None,
            "subdomain_entry": sub_entry,
            "in_cert_catalog": cert_entry is not None,
            "cert_catalog_entry": cert_entry,
            "live_cert": live_cert,
            "cert_validation_mode": validation_mode,
        },
        args.json,
    )
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Cert Lifecycle Manager (ADR 0414)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.strip(),
    )
    parser.add_argument("--json", action="store_true", dest="json", help="JSON output")
    parser.add_argument(
        "--skip-cert-validation",
        action="store_true",
        help="Skip TLS validation (for forks without Hetzner DNS API)",
    )
    parser.add_argument("--env", default="production", help="Ansible environment")

    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List all subdomains with cert status")

    # create-subdomain
    p_create = sub.add_parser("create-subdomain", help="Add subdomain + issue cert")
    p_create.add_argument("--domain", required=True, help="FQDN to create")
    p_create.add_argument("--target", required=True, help="Backend host/IP")
    p_create.add_argument("--target-port", type=int, default=443, help="Backend port")
    p_create.add_argument("--service-id", help="Service ID for catalog")
    p_create.add_argument("--apply", action="store_false", dest="dry_run", help="Apply changes")
    p_create.set_defaults(dry_run=True)

    # delete-subdomain
    p_delete = sub.add_parser("delete-subdomain", help="Remove subdomain + clean cert")
    p_delete.add_argument("--domain", required=True, help="FQDN to delete")
    p_delete.add_argument("--apply", action="store_false", dest="dry_run", help="Apply changes")
    p_delete.set_defaults(dry_run=True)

    # renew
    p_renew = sub.add_parser("renew", help="Force-renew cert for domain or all domains")
    p_renew.add_argument("--domain", help="FQDN to renew (omit for all)")
    p_renew.add_argument("--apply", action="store_false", dest="dry_run", help="Apply changes")
    p_renew.set_defaults(dry_run=True)

    # revoke
    p_revoke = sub.add_parser("revoke", help="Revoke cert for a domain")
    p_revoke.add_argument("--domain", required=True, help="FQDN to revoke")
    p_revoke.add_argument("--apply", action="store_false", dest="dry_run", help="Apply changes")
    p_revoke.set_defaults(dry_run=True)

    # sync-missing
    p_sync = sub.add_parser("sync-missing", help="Detect and repair cert mismatches (cron-safe)")
    p_sync.add_argument("--apply", action="store_false", dest="dry_run", help="Apply changes")
    p_sync.set_defaults(dry_run=True)

    # status
    p_status = sub.add_parser("status", help="Show status for a specific FQDN")
    p_status.add_argument("--domain", required=True, help="FQDN to check")

    args = parser.parse_args()

    # Propagate global flags to subcommand namespace
    for flag in ("json", "skip_cert_validation", "env"):
        if not hasattr(args, flag):
            setattr(args, flag, getattr(parser.parse_args([args.command] + sys.argv[2:]), flag, None))

    commands = {
        "list": cmd_list,
        "create-subdomain": cmd_create_subdomain,
        "delete-subdomain": cmd_delete_subdomain,
        "renew": cmd_renew,
        "revoke": cmd_revoke,
        "sync-missing": cmd_sync_missing,
        "status": cmd_status,
    }

    fn = commands.get(args.command)
    if fn is None:
        print(f"[error] Unknown command: {args.command}", file=sys.stderr)
        sys.exit(2)

    sys.exit(fn(args))


if __name__ == "__main__":
    main()
