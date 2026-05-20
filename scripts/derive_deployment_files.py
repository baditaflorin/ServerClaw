"""Derive identity.yml, connection.yml, profile.yml from .local/manifest.yml.

ADR 0483 §3 step 0 (`derive-deployment-files`). The operator authors exactly
one file — `.local/manifest.yml` — and this script produces the three
derived files the rest of the bootstrap chain consumes.

The mapping is straight projection from manifest.schema.json:

    manifest.apex_domain          -> identity.platform_domain
    manifest.operator.name/email  -> identity.platform_operator_{name,email}
    manifest.provider.host/port   -> connection.proxmox_host.{addr,port}
    manifest.provider.initial_*   -> connection.proxmox_host.{user,key}
    manifest.profiles             -> profile.profiles
    manifest.extra_services       -> profile.extra_services
    manifest.disabled_services    -> profile.disabled_services

The script is idempotent: writing it twice produces identical output.
Validates every emitted file against its schema before persisting.

Usage:
    uv run --with pyyaml --with jsonschema python scripts/derive_deployment_files.py

Exit codes:
  0  all three files written and schema-valid
  2  manifest.yml missing or invalid
  3  output validation failed (schema regression — investigate)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"
SCHEMA_DIR = REPO_ROOT / "config" / "contracts" / "deployment-v1"

MANIFEST_PATH = LOCAL_ROOT / "manifest.yml"
IDENTITY_PATH = LOCAL_ROOT / "identity.yml"
CONNECTION_PATH = LOCAL_ROOT / "connection.yml"
PROFILE_PATH = LOCAL_ROOT / "profile.yml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _validate(instance: dict[str, Any], schema_name: str) -> None:
    schema = json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text())
    jsonschema.validate(instance=instance, schema=schema)


def derive_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    apex = manifest["apex_domain"]
    operator = manifest["operator"]
    derived: dict[str, Any] = {
        "platform_domain": apex,
        "platform_operator_email": operator["email"],
        "platform_operator_name": operator["name"],
        "platform_config_prefix": apex.split(".")[0],
        "hetzner_dns_zone_name": apex,
        "platform_guest_network_cidr": manifest.get("platform_guest_network_cidr", "10.10.10.0/24"),
        "platform_tailscale_network_cidr": manifest.get("platform_tailscale_network_cidr", "100.64.0.0/10"),
    }
    extra_vars = manifest.get("extra_vars") or {}
    if extra_vars:
        clash = sorted(set(derived) & set(extra_vars))
        if clash:
            raise ValueError(
                "manifest.extra_vars contains keys that clash with derived identity fields: "
                f"{', '.join(clash)}. Remove them from extra_vars or use a first-class manifest field."
            )
        derived.update(extra_vars)
    return derived


def derive_connection(manifest: dict[str, Any]) -> dict[str, Any]:
    provider = manifest["provider"]
    return {
        "schema_version": 1,
        "proxmox_host": {
            "addr": provider["host"],
            "port": int(provider.get("port", 22)),
            "user": provider["initial_user"],
            "key": provider["initial_key_path"],
        },
        "guest_ssh": {
            "user": "ops",
            "key": "bootstrap.id_ed25519",
            "jump_user": provider["initial_user"],
            "jump_via": "proxmox_host",
        },
    }


def derive_profile(manifest: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"profiles": list(manifest.get("profiles") or ["core"])}
    if manifest.get("extra_services"):
        out["extra_services"] = list(manifest["extra_services"])
    if manifest.get("disabled_services"):
        out["disabled_services"] = list(manifest["disabled_services"])
    return out


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    if not MANIFEST_PATH.is_file():
        print(
            f"ERROR: {MANIFEST_PATH} not found.\n"
            "Author .local/manifest.yml first — see "
            "config/contracts/deployment-v1/manifest.schema.json for the shape.",
            file=sys.stderr,
        )
        return 2
    manifest = _load_yaml(MANIFEST_PATH)
    try:
        _validate(manifest, "manifest")
    except jsonschema.ValidationError as e:
        print(f"ERROR: manifest.yml schema violation at {list(e.absolute_path)}: {e.message}", file=sys.stderr)
        return 2

    try:
        identity = derive_identity(manifest)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    connection = derive_connection(manifest)
    profile = derive_profile(manifest)

    try:
        _validate(identity, "identity")
        _validate(connection, "connection")
        _validate(profile, "profile")
    except jsonschema.ValidationError as e:
        print(f"ERROR: derived output failed schema check: {e.message}", file=sys.stderr)
        return 3

    _write(IDENTITY_PATH, identity)
    _write(CONNECTION_PATH, connection)
    _write(PROFILE_PATH, profile)

    print(f"wrote {IDENTITY_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {CONNECTION_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {PROFILE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
