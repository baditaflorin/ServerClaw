#!/usr/bin/env python3
"""Validate topology YAML files against the deployment-v1 topology schema.

ADR 0462 — pre-commit gate that catches malformed topology files before
they reach the runtime loader. The 2026-04-28 incident
(.local/deployments/0fork/topology.yml missing `role` on each guest)
silently broke generate_platform_vars.py 30 minutes deep into a
converge. ws-0448 patched the loader to auto-fill `role` from `name`,
but the right move is to reject malformed shapes at commit time.

Validates:
  - inventory/host_vars/proxmox-host.yml (committed canonical topology)
  - .local/deployments/<slug>/topology.yml (per-deployment overlays,
    when present at run time — pre-commit hook only touches committed
    paths so it skips .local/ silently)

Usage:

    python3 scripts/validate_topology_schema.py [PATH...]

When invoked with no PATH, validates the committed
`inventory/host_vars/proxmox-host.yml` and any
`.local/deployments/*/topology.yml` it can find. When invoked by
pre-commit, the staged paths are passed as arguments and only those
are validated.

Exit codes:
  0 — every input file matches the topology schema
  1 — at least one schema violation
  2 — usage / data error (file unreadable, schema missing, etc.)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "config" / "contracts" / "deployment-v1" / "topology.schema.json"
COMMITTED_HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
DEPLOYMENTS_DIR = REPO_ROOT / ".local" / "deployments"


def _load_schema() -> dict:
    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"topology schema missing: {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for validate_topology_schema.py") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level must be a mapping")
    return data


def _looks_like_topology(path: Path) -> bool:
    """Heuristic: a file is a topology when it has `proxmox_guests` at the top.

    The committed `inventory/host_vars/proxmox-host.yml` and the
    per-deployment `topology.yml` files both expose `proxmox_guests`.
    Other YAML files (group_vars, role defaults, playbooks) usually do
    not. Pre-commit can hand us anything that matches the file glob,
    so we skip files that don't look like topology.

    Returns False on any parse error — unparseable YAML is not our
    problem to flag here (other hooks do that).
    """
    try:
        data = _load_yaml(path)
    except Exception:
        return False
    return isinstance(data, dict) and "proxmox_guests" in data


def validate_one(path: Path, schema: dict) -> list[str]:
    """Return a list of human-readable schema-violation strings (empty when valid).

    Uses jsonschema if available; falls back to a minimal required-keys
    check if not (so the hook works on a fresh checkout before
    `uv pip install jsonschema`).
    """
    try:
        data = _load_yaml(path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return [f"{path}: {exc}"]

    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        # Minimal fallback — top-level proxmox_guests with at least one
        # entry having name/vmid/ipv4. This is a strict subset of the
        # schema; full validation requires jsonschema.
        guests = data.get("proxmox_guests")
        if not isinstance(guests, list) or not guests:
            return [f"{path}: proxmox_guests must be a non-empty list"]
        errors: list[str] = []
        for index, guest in enumerate(guests):
            if not isinstance(guest, dict):
                errors.append(f"{path}:proxmox_guests[{index}]: must be a mapping")
                continue
            for required in ("name", "vmid", "ipv4"):
                if required not in guest:
                    errors.append(f"{path}:proxmox_guests[{index}]: missing required field '{required}'")
        return errors

    validator = Draft202012Validator(schema)
    errors = []
    for err in validator.iter_errors(data):
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}:{loc}: {err.message}")
    return errors


def discover_topology_files(explicit: list[Path]) -> list[Path]:
    """Resolve which paths to validate.

    - If explicit paths are passed, use those (filtered to ones that
      look like topology files).
    - Otherwise, default to the committed proxmox-host.yml plus any
      .local/deployments/*/topology.yml.
    """
    if explicit:
        return [p for p in explicit if _looks_like_topology(p)]
    candidates: list[Path] = []
    if COMMITTED_HOST_VARS.is_file():
        candidates.append(COMMITTED_HOST_VARS)
    if DEPLOYMENTS_DIR.is_dir():
        for slug_dir in sorted(DEPLOYMENTS_DIR.iterdir()):
            if not slug_dir.is_dir() or slug_dir.name.startswith("."):
                continue
            tpl = slug_dir / "topology.yml"
            if tpl.is_file():
                candidates.append(tpl)
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validate_topology_schema", description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="Topology YAML files to validate. Empty = default set.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only on error.",
    )
    args = parser.parse_args(argv)

    try:
        schema = _load_schema()
    except FileNotFoundError as exc:
        print(f"validate_topology_schema: {exc}", file=sys.stderr)
        return 2

    paths = discover_topology_files(args.paths)
    if not paths:
        if not args.quiet:
            print("validate_topology_schema: no topology files found.")
        return 0

    failed = 0
    for path in paths:
        errors = validate_one(path, schema)
        if errors:
            failed += 1
            for err in errors:
                print(f"validate_topology_schema: {err}", file=sys.stderr)
        elif not args.quiet:
            print(f"validate_topology_schema: OK {path}")

    if failed:
        print(f"validate_topology_schema: {failed} file(s) failed schema validation.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
