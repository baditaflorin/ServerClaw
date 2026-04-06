#!/usr/bin/env python3
"""Generate cross-cutting infrastructure artifacts from the platform service registry.

ADR 0374 — Cross-Cutting Service Manifest.

Each service in platform_service_registry declares what it needs from DNS, nginx,
TLS, and SSO in one place. This script reads those declarations and generates or
validates the corresponding artifacts.

Usage:
    # Validate all concerns (check mode — no files written)
    python scripts/generate_cross_cutting_artifacts.py --check

    # Generate all concerns
    python scripts/generate_cross_cutting_artifacts.py --write

    # Generate or validate only a specific concern
    python scripts/generate_cross_cutting_artifacts.py --check --only sso
    python scripts/generate_cross_cutting_artifacts.py --write --only sso

Concerns (phases):
    hairpin  — platform_hairpin_nat_hosts list for compose extra_hosts
    dns      — Hetzner DNS A record declarations
    tls      — certificate-catalog.json domain entries
    proxy    — nginx edge server-block fragments
    sso      — Keycloak OIDC client declarations

This script MUST NOT:
    - Make live API calls (no Hetzner DNS API, no Keycloak API, no cert issuance)
    - Import requests at module load time (breaks --export-mcp validation container)
    - Modify files outside of config/generated/, config/subdomain-catalog.json,
      config/certificate-catalog.json, and inventory/group_vars/platform_hairpin.yml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402 — must come after sys.path adjustment
from validation_toolkit import require_bool, require_list, require_mapping, require_str  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform_services.yml"

VALID_CONCERNS = ("hairpin", "dns", "tls", "proxy", "sso")
VALID_SSO_PROVIDERS = {"keycloak", "oauth2-proxy"}

# Scopes considered sensitive — warn when present on a public client
_SENSITIVE_SCOPES = {"roles", "groups", "offline_access"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict:
    with REGISTRY_PATH.open() as f:
        data = yaml.safe_load(f)
    registry = require_mapping(data, str(REGISTRY_PATH))
    return require_mapping(registry.get("platform_service_registry", {}), "platform_service_registry")


# ---------------------------------------------------------------------------
# SSO concern (Phase 5)
# ---------------------------------------------------------------------------


def generate_sso_clients(registry: dict, write: bool = False, repo_root: Path = REPO_ROOT) -> dict:
    """Generate SSO client declarations from registry sso sections.

    Returns a mapping of client_id -> client declaration dict.
    Raises ValueError on any validation error.
    """
    clients: dict[str, dict] = {}
    # Track which service claimed each client_id to give a useful duplicate error
    client_owners: dict[str, str] = {}

    for service_name, service_config in registry.items():
        service_config = require_mapping(service_config, f"platform_service_registry.{service_name}")
        sso_config = service_config.get("sso")
        if sso_config is None:
            continue

        path_prefix = f"platform_service_registry.{service_name}.sso"
        sso_config = require_mapping(sso_config, path_prefix)

        enabled = sso_config.get("enabled", False)
        if not require_bool(enabled, f"{path_prefix}.enabled"):
            continue

        client_id = require_str(
            sso_config.get("client_id"),
            f"{path_prefix}.client_id",
        )

        provider = require_str(
            sso_config.get("provider", "keycloak"),
            f"{path_prefix}.provider",
        )
        if provider not in VALID_SSO_PROVIDERS:
            raise ValueError(
                f"{path_prefix}.provider must be one of: {', '.join(sorted(VALID_SSO_PROVIDERS))}"
            )

        redirect_uris_raw = sso_config.get("redirect_uris", [])
        redirect_uris = require_list(redirect_uris_raw, f"{path_prefix}.redirect_uris")
        for idx, uri in enumerate(redirect_uris):
            require_str(uri, f"{path_prefix}.redirect_uris[{idx}]")

        scopes = sso_config.get("scopes", ["openid", "profile", "email"])
        require_list(scopes, f"{path_prefix}.scopes")
        for idx, scope in enumerate(scopes):
            require_str(scope, f"{path_prefix}.scopes[{idx}]")

        public_client = sso_config.get("public_client", False)
        require_bool(public_client, f"{path_prefix}.public_client")

        # Validate redirect_uri format
        _validate_redirect_uris(redirect_uris, path_prefix)

        # Warn: public client with sensitive scopes
        sensitive_present = set(scopes) & _SENSITIVE_SCOPES
        if public_client and sensitive_present:
            print(
                f"  WARNING: {path_prefix}: public_client=true but scopes include "
                f"sensitive: {sorted(sensitive_present)}"
            )

        # Duplicate client_id check
        if client_id in client_owners:
            raise ValueError(
                f"Duplicate SSO client_id '{client_id}': claimed by "
                f"'{client_owners[client_id]}' and '{service_name}'"
            )

        client_owners[client_id] = service_name

        # client_secret_local_file is optional (service accounts may have none)
        client_secret_local_file = sso_config.get("client_secret_local_file")
        if client_secret_local_file is not None:
            require_str(client_secret_local_file, f"{path_prefix}.client_secret_local_file")

        clients[client_id] = {
            "service": service_name,
            "provider": provider,
            "redirect_uris": redirect_uris,
            "scopes": scopes,
            "public_client": public_client,
        }

    if write:
        out_dir = repo_root / "config" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "sso-clients.yaml"
        header = (
            "# GENERATED — do not edit. Regenerate: "
            "python scripts/generate_cross_cutting_artifacts.py --write --only sso\n"
        )
        body = yaml.dump({"sso_clients": clients}, default_flow_style=False, sort_keys=True)
        out_path.write_text(header + body)
        print(f"  Wrote {len(clients)} SSO client declarations to {out_path.relative_to(repo_root)}")
    else:
        print(f"  SSO: {len(clients)} client declarations validated (no files written)")

    return clients


def _validate_redirect_uris(redirect_uris: list, path_prefix: str) -> None:
    """Validate redirect URI format. Non-localhost URIs must be HTTPS."""
    import re

    for idx, uri in enumerate(redirect_uris):
        uri_path = f"{path_prefix}.redirect_uris[{idx}]"
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError(f"{uri_path} must be a non-empty string")

        # Allow localhost/127.0.0.1 with http (common for CLI OAuth callbacks)
        _localhost_pattern = re.compile(
            r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/.*)?$"
        )
        if uri.startswith("http://") and not _localhost_pattern.match(uri):
            raise ValueError(
                f"{uri_path}: non-localhost redirect URIs must use HTTPS (got: {uri!r})"
            )

        if not (uri.startswith("https://") or uri.startswith("http://")):
            raise ValueError(
                f"{uri_path}: redirect URI must start with https:// or http:// (got: {uri!r})"
            )


# ---------------------------------------------------------------------------
# Stub generators for other concerns (phases 1-4)
# These are called when --only is not specified, so they must exist.
# ---------------------------------------------------------------------------


def _concern_not_implemented(concern: str, write: bool = False) -> None:
    """Placeholder for concerns not yet implemented in this script."""
    mode = "write" if write else "check"
    print(f"  {concern}: not yet implemented in this script (--{mode} no-op)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or validate cross-cutting infrastructure artifacts — ADR 0374.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Concerns:
  hairpin  platform_hairpin_nat_hosts list for compose extra_hosts (Phase 1)
  dns      Hetzner DNS A record declarations (Phase 2)
  tls      certificate-catalog.json domain entries (Phase 3)
  proxy    nginx edge server-block fragments (Phase 4)
  sso      Keycloak OIDC client declarations (Phase 5)

Examples:
  python scripts/generate_cross_cutting_artifacts.py --check
  python scripts/generate_cross_cutting_artifacts.py --write --only sso
""",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate only; no files written")
    mode.add_argument("--write", action="store_true", help="Write generated artifacts to disk")
    parser.add_argument(
        "--only",
        choices=list(VALID_CONCERNS),
        metavar="CONCERN",
        help=f"Process only this concern. One of: {', '.join(VALID_CONCERNS)}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    write = args.write
    only = args.only

    print(f"Loading registry from {REGISTRY_PATH.relative_to(REPO_ROOT)} ...")
    try:
        registry = _load_registry()
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: Failed to load registry: {exc}", file=sys.stderr)
        return 1

    concerns_to_run = [only] if only else list(VALID_CONCERNS)

    errors: list[str] = []

    for concern in concerns_to_run:
        print(f"\n[{concern.upper()}]")
        try:
            if concern == "sso":
                generate_sso_clients(registry, write=write, repo_root=REPO_ROOT)
            else:
                _concern_not_implemented(concern, write=write)
        except ValueError as exc:
            msg = f"ERROR ({concern}): {exc}"
            print(f"  {msg}", file=sys.stderr)
            errors.append(msg)
        except Exception as exc:  # noqa: BLE001
            msg = f"UNEXPECTED ERROR ({concern}): {type(exc).__name__}: {exc}"
            print(f"  {msg}", file=sys.stderr)
            errors.append(msg)

    if errors:
        print(f"\nFailed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nAll concerns passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
