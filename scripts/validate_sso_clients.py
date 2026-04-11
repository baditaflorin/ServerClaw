#!/usr/bin/env python3
"""Validate the generated SSO client declarations.

ADR 0374 — Cross-Cutting Service Manifest, Phase 5 (SSO).

Loads config/generated/sso-clients.yaml and checks:
  1. Each client has at least one redirect_uri (warning for service accounts).
  2. All redirect_uris are valid HTTPS URLs (http:// allowed only for localhost).
  3. Warns if public_client=true and scopes include sensitive ones.
  4. No duplicate client_names within the file.
  5. Required fields are present and correctly typed.

Usage:
    python scripts/validate_sso_clients.py --check   # exit 0 if valid, 1 on error
    python scripts/validate_sso_clients.py --list    # print all declared clients

This script does NOT make live Keycloak API calls.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from validation_toolkit import require_bool, require_list, require_mapping, require_str

REPO_ROOT = Path(__file__).resolve().parents[1]
SSO_CLIENTS_PATH = REPO_ROOT / "config" / "generated" / "sso-clients.yaml"

# Scopes that carry elevated privilege and should not be on public clients
_SENSITIVE_SCOPES = {"roles", "groups", "offline_access"}

# Pattern for localhost redirect URIs (http:// is acceptable)
_LOCALHOST_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/.*)?$")

# Pattern for HTTPS URIs
_HTTPS_RE = re.compile(r"^https://")


def _load_sso_clients() -> dict:
    if not SSO_CLIENTS_PATH.exists():
        raise FileNotFoundError(
            f"{SSO_CLIENTS_PATH.relative_to(REPO_ROOT)} does not exist. "
            "Run: python scripts/generate_cross_cutting_artifacts.py --write --only sso"
        )
    with SSO_CLIENTS_PATH.open() as f:
        data = yaml.safe_load(f)
    doc = require_mapping(data, str(SSO_CLIENTS_PATH))
    return require_mapping(doc.get("sso_clients", {}), "sso_clients")


def validate_clients(clients: dict) -> tuple[list[str], list[str]]:
    """Validate all client declarations. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    seen_client_ids: set[str] = set()

    for client_id, client_config in clients.items():
        path = f"sso_clients.{client_id}"

        # Duplicate check (the generator should prevent this, but verify anyway)
        if client_id in seen_client_ids:
            errors.append(f"{path}: duplicate client_id '{client_id}'")
            continue
        seen_client_ids.add(client_id)

        try:
            client_config = require_mapping(client_config, path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        # Required: service
        try:
            require_str(client_config.get("service"), f"{path}.service")
        except ValueError as exc:
            errors.append(str(exc))

        # Required: provider
        provider = client_config.get("provider", "keycloak")
        try:
            require_str(provider, f"{path}.provider")
        except ValueError as exc:
            errors.append(str(exc))

        # Required: redirect_uris (list)
        redirect_uris = client_config.get("redirect_uris", [])
        try:
            redirect_uris = require_list(redirect_uris, f"{path}.redirect_uris")
        except ValueError as exc:
            errors.append(str(exc))
            redirect_uris = []

        # Warn if no redirect_uris (service accounts legitimately have none)
        if not redirect_uris:
            warnings.append(
                f"{path}: no redirect_uris declared. "
                "This is expected for service-account clients; "
                "add redirect_uris if this is a browser-flow client."
            )
        else:
            # Validate each URI
            for idx, uri in enumerate(redirect_uris):
                uri_path = f"{path}.redirect_uris[{idx}]"
                if not isinstance(uri, str) or not uri.strip():
                    errors.append(f"{uri_path}: must be a non-empty string")
                    continue

                # Non-localhost http:// is rejected
                if uri.startswith("http://") and not _LOCALHOST_RE.match(uri):
                    errors.append(f"{uri_path}: non-localhost redirect URIs must use HTTPS (got: {uri!r})")
                elif not uri.startswith("https://") and not uri.startswith("http://"):
                    errors.append(f"{uri_path}: redirect URI must start with https:// or http:// (got: {uri!r})")

        # Required: scopes (list)
        scopes = client_config.get("scopes", [])
        try:
            scopes = require_list(scopes, f"{path}.scopes")
        except ValueError as exc:
            errors.append(str(exc))
            scopes = []

        # Required: public_client (bool)
        public_client = client_config.get("public_client", False)
        try:
            public_client = require_bool(public_client, f"{path}.public_client")
        except ValueError as exc:
            errors.append(str(exc))
            public_client = False

        # Warn: public client with sensitive scopes
        if public_client:
            sensitive_present = set(scopes) & _SENSITIVE_SCOPES
            if sensitive_present:
                warnings.append(
                    f"{path}: public_client=true but scopes include sensitive: "
                    f"{sorted(sensitive_present)}. Consider using a confidential client."
                )

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the generated SSO client declarations — ADR 0374 Phase 5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The source file is config/generated/sso-clients.yaml (produced by
generate_cross_cutting_artifacts.py --write --only sso).

This script does NOT make live Keycloak API calls.
""",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate and exit (0 = ok, 1 = error)")
    mode.add_argument("--list", action="store_true", help="List all declared SSO clients")
    args = parser.parse_args(argv)

    try:
        clients = _load_sso_clients()
    except (FileNotFoundError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.list:
        print(f"SSO clients in {SSO_CLIENTS_PATH.relative_to(REPO_ROOT)}:")
        print(f"  {'CLIENT ID':<35} {'SERVICE':<25} {'PROVIDER':<15} {'PUBLIC'}")
        print(f"  {'-' * 35} {'-' * 25} {'-' * 15} {'-' * 6}")
        for client_id, cfg in sorted(clients.items()):
            service = cfg.get("service", "?")
            provider = cfg.get("provider", "?")
            pub = str(cfg.get("public_client", False))
            uris = len(cfg.get("redirect_uris", []))
            print(f"  {client_id:<35} {service:<25} {provider:<15} {pub}  ({uris} redirect URI(s))")
        print(f"\nTotal: {len(clients)} client(s)")
        return 0

    # --check mode
    print(f"Validating {SSO_CLIENTS_PATH.relative_to(REPO_ROOT)} ({len(clients)} client(s)) ...")
    errors, warnings = validate_clients(clients)

    for warning in warnings:
        print(f"  WARNING: {warning}")

    if errors:
        print(f"\nValidation FAILED — {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1

    print(f"\nValidation passed: {len(clients)} client(s) checked, {len(warnings)} warning(s), 0 error(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
