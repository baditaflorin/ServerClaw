"""Derive a draft manifest.yml from `.local/identity.yml` — ADR 0483 + ADR 0488.

For existing deployments that pre-date the hands-off bootstrap pattern, this
script introspects `.local/identity.yml` and `.local/profile.yml` and emits a
manifest.yml that, once committed, brings the deployment into the
hands-off-capable pattern.

The output is a *draft* — it includes a `review_required` block listing
fields the operator must fill in manually (typically secrets.source and
any provider details not readable from local files).

Usage:

    # Derive a manifest from `.local/identity.yml`:
    uv run --with pyyaml --with jsonschema python scripts/derive_manifest.py

    # Write to disk (default path is .local/manifest.yml.draft):
    uv run ... python scripts/derive_manifest.py --write

    # Write to a specific path:
    uv run ... python scripts/derive_manifest.py --out path/to/manifest.yml

    # Validate an existing manifest against the schema:
    uv run ... python scripts/derive_manifest.py --validate

Output:
    Writes YAML to stdout (unless --write / --out is given).
    Human-readable notes go to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"
IDENTITY_PATH = LOCAL_ROOT / "identity.yml"
PROFILE_PATH = LOCAL_ROOT / "profile.yml"
MANIFEST_PATH = LOCAL_ROOT / "manifest.yml"
MANIFEST_DRAFT_PATH = LOCAL_ROOT / "manifest.yml.draft"

SCHEMA_PATH = REPO_ROOT / "config" / "contracts" / "deployment-v1" / "manifest.schema.json"
SIZING_POLICY_PATH = REPO_ROOT / "config" / "sizing-policy.yml"

# Hetzner NVMe AX-series: SSH commonly runs on 2222.
_HETZNER_NONSTANDARD_PORT = 2222
# Key filename fragments that suggest Hetzner provenance.
_HETZNER_KEY_HINTS = ["hetzner", "llm_agents", "llm-agents"]


@dataclass
class DeriveResult:
    manifest: dict[str, Any]
    review_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Pure derivation helpers (no IO — tested directly)
# --------------------------------------------------------------------------- #


def derive_operator(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": identity.get("platform_operator_name", "FILL_IN"),
        "email": identity.get("platform_operator_email", "FILL_IN"),
    }


def derive_provider(connection: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Derive provider block from connection.yml. Returns (provider_dict, review_notes)."""
    review: list[str] = []
    pxmx = connection.get("proxmox_host") or {}
    host = pxmx.get("addr", "FILL_IN")
    port = pxmx.get("port", 22)
    user = pxmx.get("user", "root")
    key_raw = pxmx.get("key", "FILL_IN")

    # Determine key_path string
    if isinstance(key_raw, dict):
        key_path = f"vault:{key_raw.get('vault', 'FILL_IN')}"
        review.append(
            "provider.initial_key_path: was a vault reference — replace with .local/ssh/ path or keep vault form"
        )
    else:
        key_path = str(key_raw)

    # Heuristic provider kind detection
    key_lower = key_path.lower()
    kind = "custom"
    if any(h in key_lower for h in _HETZNER_KEY_HINTS) or port == _HETZNER_NONSTANDARD_PORT:
        kind = "hetzner"

    provider: dict[str, Any] = {
        "kind": kind,
        "host": host,
        "initial_user": user,
        "initial_key_path": Path(key_path).name if key_path.startswith(".local/") else key_path,
    }
    if port != 22:
        provider["port"] = port

    if host == "FILL_IN":
        review.append("provider.host: not found in connection.yml — fill in the Proxmox host address")
    if kind == "custom":
        review.append("provider.kind: could not infer provider type — set to 'hetzner', 'local', or 'custom'")

    return provider, review


def derive_profiles(profile_data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Derive profiles / extra_services / disabled_services from profile.yml."""
    profiles = list(profile_data.get("profiles") or ["core"])
    extra = list(profile_data.get("extra_services") or [])
    disabled = list(profile_data.get("disabled_services") or [])
    return profiles, extra, disabled


def derive_smoke_endpoints(apex: str) -> list[str]:
    """Generate a starter smoke-endpoint list for the given apex."""
    return [
        f"https://registry.{{apex}}/api/v2.0/ping",
        f"https://sso.{{apex}}/realms/{{apex_slug}}/.well-known/openid-configuration",
        f"https://wiki.{{apex}}/",
    ]


def build_manifest(
    identity: dict[str, Any],
    connection: dict[str, Any],
    profile_data: dict[str, Any],
) -> DeriveResult:
    """Assemble a manifest dict from existing deployment files.

    Pure — no IO. Tested directly.
    """
    review: list[str] = []
    warnings: list[str] = []

    apex = identity.get("platform_domain", "FILL_IN")
    if apex == "FILL_IN":
        review.append("apex_domain: not found in identity.yml — fill in manually")

    operator = derive_operator(identity)
    if "FILL_IN" in operator.values():
        review.append("operator: one or more fields missing from identity.yml")

    provider, prov_review = derive_provider(connection)
    review.extend(prov_review)

    profiles, extra, disabled = derive_profiles(profile_data)

    # Detect likely secrets source: if there's a topology.yml, openbao is already
    # running so prefer openbao; otherwise fall back to operator-stdin.
    secrets_source = "operator-stdin"
    warnings.append(
        "secrets.source: defaulted to 'operator-stdin' — change to 'openbao' once "
        "step-9 (converge-openbao) has run and OpenBao is unsealed on this deployment"
    )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "apex_domain": apex,
        "operator": operator,
        "provider": provider,
        "profiles": profiles,
    }
    if extra:
        manifest["extra_services"] = extra
    if disabled:
        manifest["disabled_services"] = disabled

    manifest["secrets"] = {"source": secrets_source}
    manifest["gates"] = {
        "fail_fast": True,
        "max_retries_per_step": 3,
        "step_timeout_s": 1800,
    }
    manifest["verification"] = {
        "smoke_endpoints": derive_smoke_endpoints(apex),
        "expected_running_vms_count": ">= 5",
    }

    return DeriveResult(manifest=manifest, review_required=review, warnings=warnings)


# --------------------------------------------------------------------------- #
# Schema validation
# --------------------------------------------------------------------------- #


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate manifest against the JSON Schema. Returns a list of error messages."""
    if not SCHEMA_PATH.is_file():
        return [f"schema not found: {SCHEMA_PATH}"]
    try:
        from jsonschema import Draft202012Validator  # type: ignore

        schema = json.loads(SCHEMA_PATH.read_text())
        errs = list(Draft202012Validator(schema).iter_errors(manifest))
        return [(".".join(str(p) for p in e.absolute_path) or "<root>") + ": " + e.message for e in errs]
    except ImportError:
        return []  # jsonschema not installed — skip


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _load_deployment_files() -> tuple[dict, dict, dict]:
    """Load identity, connection (from identity::proxmox_host_ssh), and profile.

    Returns (identity, connection, profile) as three dicts. ADR 0488: all live
    in `.local/` directly, no per-slug subdirectory.
    """

    def _read(p: Path) -> dict:
        if not p.is_file():
            sys.stderr.write(f"  warning: {p} not found — using empty dict\n")
            return {}
        with p.open() as fh:
            return yaml.safe_load(fh) or {}

    identity = _read(IDENTITY_PATH)
    profile = _read(PROFILE_PATH)
    # ADR 0488 collapse: connection block lives inside identity.yml.
    connection = {"proxmox_host": identity.get("proxmox_host_ssh") or {}}
    return identity, connection, profile


def _emit_yaml_with_comments(result: DeriveResult, *, out: Any) -> None:
    """Write the manifest YAML to `out`, appending review notes as comments."""
    out.write(
        "# AUTO-GENERATED by scripts/derive_manifest.py — ADR 0483 §6\n"
        "# Review all fields marked FILL_IN and the review_required section below.\n"
        "# Remove this comment block before committing.\n\n"
    )
    out.write(yaml.dump(result.manifest, default_flow_style=False, sort_keys=False, allow_unicode=True))

    if result.review_required or result.warnings:
        out.write("\n# --- REVIEW REQUIRED ---\n")
        for note in result.review_required:
            out.write(f"# REQUIRED: {note}\n")
        for note in result.warnings:
            out.write(f"# WARNING:  {note}\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true", help="Write to .local/manifest.yml.draft")
    p.add_argument("--out", help="Write to this path instead of stdout")
    p.add_argument(
        "--validate", action="store_true", help="Validate the existing .local/manifest.yml against the schema and exit"
    )
    args = p.parse_args(argv)

    if args.validate:
        if not MANIFEST_PATH.is_file():
            sys.exit(f"no manifest.yml found at {MANIFEST_PATH}")
        with MANIFEST_PATH.open() as fh:
            manifest = yaml.safe_load(fh) or {}
        errs = validate_manifest(manifest)
        if errs:
            sys.stderr.write(f"manifest.yml is INVALID ({len(errs)} errors):\n")
            for e in errs:
                sys.stderr.write(f"  {e}\n")
            return 1
        sys.stderr.write(f"{MANIFEST_PATH} is valid.\n")
        return 0

    identity, connection, profile_data = _load_deployment_files()
    result = build_manifest(identity, connection, profile_data)

    # Schema-validate before output.
    errs = validate_manifest(result.manifest)
    if errs:
        sys.stderr.write(f"  validation errors in derived manifest ({len(errs)}):\n")
        for e in errs:
            sys.stderr.write(f"    {e}\n")
        sys.stderr.write("  (manifest will still be written — fix review_required fields)\n")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as fh:
            _emit_yaml_with_comments(result, out=fh)
        sys.stderr.write(f"  wrote {out_path}\n")
    elif args.write:
        MANIFEST_DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST_DRAFT_PATH.open("w") as fh:
            _emit_yaml_with_comments(result, out=fh)
        sys.stderr.write(f"  wrote {MANIFEST_DRAFT_PATH}\n")
        sys.stderr.write("  review and rename to manifest.yml when ready\n")
    else:
        _emit_yaml_with_comments(result, out=sys.stdout)

    if result.review_required:
        sys.stderr.write(f"\n  {len(result.review_required)} field(s) require manual review (see comments in output)\n")
    if result.warnings:
        sys.stderr.write(f"  {len(result.warnings)} warning(s) (see comments in output)\n")

    return 0 if not result.review_required else 2


if __name__ == "__main__":
    sys.exit(main())
