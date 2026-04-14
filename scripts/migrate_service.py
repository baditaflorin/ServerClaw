#!/usr/bin/env python3
"""Move a service from one VM to another — single canonical IaC entrypoint.

ADR 0417 — Service VM Migration IaC.

All VM migrations MUST go through this script. Manual registry edits for
migrations are deprecated. The script:
  1. Updates all registry fields that encode VM assignment atomically
  2. Validates topology consistency (ADR 0416)
  3. Runs the correct ordered converge sequence (postgres → stop-old → service → nginx)
  4. Writes a migration receipt

Registries updated (authoritative first):
  platform_services.yml              host_group              (AUTHORITATIVE)
  platform_services.yml              proxy.upstream_host     (derived — updated to match)
  inventory/host_vars/proxmox-host.yml  lv3_service_topology.owning_vm  (updated to match)
  inventory/host_vars/proxmox-host.yml  Jinja2 VM refs in topology block (updated to match)

Usage:
    python scripts/migrate_service.py --svc keycloak --to runtime-control --dry-run
    python scripts/migrate_service.py --svc keycloak --to runtime-control --execute
    python scripts/migrate_service.py --svc keycloak --to runtime-control --execute --env staging
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVICES_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
POSTGRES_CLIENTS_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform_postgres.yml"
PROXMOX_HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
PLATFORM_YML_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
RECEIPTS_DIR = REPO_ROOT / "receipts" / "migrations"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Any:
    with path.open() as f:
        return yaml.safe_load(f)


def load_service_registry() -> dict[str, dict]:
    raw = _load_yaml(SERVICES_PATH)
    return raw.get("platform_service_registry", {})


def load_postgres_clients() -> list[dict]:
    raw = _load_yaml(POSTGRES_CLIENTS_PATH)
    return raw.get("platform_postgres_clients", [])


def load_topology() -> dict[str, Any]:
    raw = _load_yaml(PROXMOX_HOST_VARS_PATH)
    return raw.get("lv3_service_topology", {})


def load_known_guests() -> set[str]:
    try:
        raw = _load_yaml(PLATFORM_YML_PATH)
        return set(raw.get("platform_guest_catalog", {}).get("by_name", {}).keys())
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# File mutation helpers — in-place text replacement, preserves formatting
# ---------------------------------------------------------------------------


def _replace_in_service_block(
    text: str,
    service_name: str,
    field_name: str,
    old_value: str,
    new_value: str,
    *,
    indent: int = 4,
) -> tuple[str, bool]:
    """Replace `field_name: old_value` within the YAML block for service_name.

    Scopes replacement to the specific service block to avoid cross-service edits.
    Returns (new_text, changed).
    """
    lines = text.splitlines(keepends=True)
    in_service = False
    # The block ends when we see a new 2-space-indent entry
    service_header_re = re.compile(rf"^  {re.escape(service_name)}:\s*$")
    next_entry_re = re.compile(r"^  [a-zA-Z_]")
    field_re = re.compile(rf"^( {{{indent}}}){re.escape(field_name)}:[ \t]+{re.escape(old_value)}")
    result = []
    changed = False
    for line in lines:
        if service_header_re.match(line):
            in_service = True
        elif next_entry_re.match(line) and in_service:
            in_service = False
        if in_service and field_re.match(line):
            line = field_re.sub(rf"\g<1>{field_name}: {new_value}", line)
            changed = True
        result.append(line)
    return "".join(result), changed


def update_platform_services(svc_name: str, from_vm: str, to_vm: str) -> list[str]:
    """Update host_group and proxy.upstream_host in platform_services.yml.

    Returns list of human-readable change descriptions.
    """
    text = SERVICES_PATH.read_text()
    changes = []

    # Update host_group (4-space indent field)
    text, changed = _replace_in_service_block(text, svc_name, "host_group", from_vm, to_vm, indent=4)
    if changed:
        changes.append(f"  platform_services.yml  {svc_name}.host_group: {from_vm} → {to_vm}")

    # Update proxy.upstream_host (6-space indent field — nested under proxy:)
    text, changed = _replace_in_service_block(text, svc_name, "upstream_host", from_vm, to_vm, indent=6)
    if changed:
        changes.append(f"  platform_services.yml  {svc_name}.proxy.upstream_host: {from_vm} → {to_vm}")

    if changes:
        SERVICES_PATH.write_text(text)
    return changes


def _find_topology_service_block(lines: list[str], svc_name: str) -> tuple[int, int] | None:
    """Return (start, end) line indices for the topology block of svc_name.

    The topology block starts at `  svc_name:` (2-space indent) and ends at
    the next 2-space-indent entry or end of file.
    """
    service_header_re = re.compile(rf"^  {re.escape(svc_name)}:\s*$")
    next_entry_re = re.compile(r"^  [a-zA-Z_]")
    start = None
    for i, line in enumerate(lines):
        if start is None and service_header_re.match(line):
            start = i
        elif start is not None and i > start and next_entry_re.match(line):
            return start, i
    if start is not None:
        return start, len(lines)
    return None


def update_proxmox_host_vars(svc_name: str, from_vm: str, to_vm: str) -> list[str]:
    """Update lv3_service_topology block for svc_name in proxmox-host.yml.

    Updates:
      - owning_vm: <from_vm>  →  owning_vm: <to_vm>
      - All Jinja2 template references  'equalto', '<from_vm>'  within the block
      - Any bare  from_vm  references in single-quoted strings within the block

    Returns list of human-readable change descriptions.
    """
    text = PROXMOX_HOST_VARS_PATH.read_text()
    lines = text.splitlines(keepends=True)

    bounds = _find_topology_service_block(lines, svc_name)
    if bounds is None:
        return []  # service not in topology — nothing to update

    start, end = bounds
    block_lines = lines[start:end]
    changes = []
    new_block = []
    for line in block_lines:
        original = line
        # owning_vm: <from_vm>
        line = re.sub(
            rf"(owning_vm:\s+){re.escape(from_vm)}\b",
            rf"\g<1>{to_vm}",
            line,
        )
        # Jinja2: selectattr('name', 'equalto', 'FROM_VM')
        line = re.sub(
            rf"(equalto',\s*'){re.escape(from_vm)}'",
            rf"\g<1>{to_vm}'",
            line,
        )
        # Other single-quoted VM references: 'FROM_VM'
        line = re.sub(
            rf"'{re.escape(from_vm)}'",
            f"'{to_vm}'",
            line,
        )
        if line != original:
            changes.append(f"  proxmox-host.yml  lv3_service_topology.{svc_name}: {from_vm!r} → {to_vm!r}")
        new_block.append(line)

    if changes:
        lines[start:end] = new_block
        PROXMOX_HOST_VARS_PATH.write_text("".join(lines))
        # Deduplicate multi-line changes to one summary
        changes = [f"  proxmox-host.yml  lv3_service_topology.{svc_name}: all refs {from_vm!r} → {to_vm!r}"]

    return changes


# ---------------------------------------------------------------------------
# Migration plan builder
# ---------------------------------------------------------------------------


def _uses_postgres(svc_name: str, postgres_clients: list[dict]) -> bool:
    return any(c.get("service") == svc_name for c in postgres_clients)


def _has_topology_entry(svc_name: str, topology: dict) -> bool:
    return svc_name in topology and isinstance(topology[svc_name], dict)


def _has_proxy(svc_name: str, registry: dict) -> bool:
    svc = registry.get(svc_name, {})
    proxy = svc.get("proxy", {})
    return bool(proxy.get("enabled"))


def _container_name(svc_name: str, registry: dict) -> str:
    return registry.get(svc_name, {}).get("container_name", svc_name)


def _health_url(svc_name: str, registry: dict) -> str | None:
    svc = registry.get(svc_name, {})
    proxy = svc.get("proxy", {})
    if proxy.get("enabled") and proxy.get("public_fqdn"):
        fqdn = proxy["public_fqdn"]
        if "{{" in fqdn:
            return None  # templated — can't resolve at script time
        return f"https://{fqdn}/health"
    return None


class MigrationStep:
    def __init__(self, description: str, make_target: str | None = None, make_vars: dict | None = None):
        self.description = description
        self.make_target = make_target
        self.make_vars = make_vars or {}

    def to_command(self, env: str) -> list[str]:
        if self.make_target is None:
            return []
        cmd = ["make", self.make_target, f"env={env}"]
        for k, v in self.make_vars.items():
            cmd.append(f"{k}={v}")
        return cmd

    def __repr__(self) -> str:
        return f"MigrationStep({self.description!r})"


def build_migration_plan(
    svc_name: str,
    from_vm: str,
    to_vm: str,
    registry: dict,
    postgres_clients: list[dict],
    topology: dict,
) -> list[MigrationStep]:
    """Return the ordered list of converge steps for this migration."""
    steps: list[MigrationStep] = []

    # Step 1 — topology consistency validation (registries already updated by caller)
    steps.append(
        MigrationStep(
            description="Validate topology consistency (ADR 0416)",
            make_target=None,  # handled specially — not a make target
        )
    )

    # Step 2 — postgres pg_hba.conf (if the service uses postgres)
    if _uses_postgres(svc_name, postgres_clients):
        steps.append(
            MigrationStep(
                description=f"Converge postgres-vm — rebuild pg_hba.conf to allow {to_vm}",
                make_target="converge-postgres-vm",
            )
        )

    # Step 3 — stop old container
    container = _container_name(svc_name, registry)
    steps.append(
        MigrationStep(
            description=f"Stop {svc_name} container ({container!r}) on {from_vm}",
            make_target="teardown-service",
            make_vars={"svc": svc_name, "on_vm": from_vm, "container_name": container},
        )
    )

    # Step 4 — converge service on new VM
    steps.append(
        MigrationStep(
            description=f"Converge {svc_name} on {to_vm}",
            make_target=f"converge-{svc_name.replace('_', '-')}",
        )
    )

    # Step 5 — nginx-edge (if service is edge-published)
    if _has_proxy(svc_name, registry) or _has_topology_entry(svc_name, topology):
        steps.append(
            MigrationStep(
                description=f"Converge nginx-edge — update upstream to {to_vm}",
                make_target="converge-nginx-edge",
            )
        )

    return steps


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------


def write_receipt(
    svc_name: str,
    from_vm: str,
    to_vm: str,
    registry_changes: list[str],
    steps: list[MigrationStep],
    env: str,
    *,
    success: bool,
    failed_step: str | None = None,
) -> Path:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H%M%SZ")
    receipt_path = RECEIPTS_DIR / f"{ts}-{svc_name}-{from_vm}-to-{to_vm}.yaml"
    receipt = {
        "schema": "migration-receipt/v1",
        "timestamp": ts,
        "service": svc_name,
        "from_vm": from_vm,
        "to_vm": to_vm,
        "env": env,
        "success": success,
        "failed_step": failed_step,
        "registry_changes": registry_changes,
        "steps": [s.description for s in steps],
        "adr": "ADR 0417",
    }
    receipt_path.write_text(yaml.dump(receipt, default_flow_style=False, allow_unicode=True))
    return receipt_path


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_step(step: MigrationStep, env: str, *, dry_run: bool) -> bool:
    """Run a single migration step. Returns True on success."""
    print(f"\n{'[dry-run] ' if dry_run else ''}▶ {step.description}")

    if step.make_target is None:
        # topology validation — special case
        cmd = [
            "uv",
            "run",
            "--with",
            "pyyaml",
            "python",
            str(REPO_ROOT / "scripts" / "validate_topology_consistency.py"),
            "--check",
        ]
    else:
        cmd = step.to_command(env)

    print(f"  $ {' '.join(cmd)}")

    if dry_run:
        return True

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"\n✗ Step failed: {step.description}")
        print(f"  Command: {' '.join(cmd)}")
        return False
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svc", required=True, help="Service name (e.g. keycloak)")
    parser.add_argument("--to", required=True, dest="to_vm", help="Target VM (e.g. runtime-control)")
    parser.add_argument("--env", default="production", help="Ansible env (default: production)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    mode.add_argument("--execute", action="store_true", help="Execute migration")
    args = parser.parse_args()

    svc_name = args.svc
    to_vm = args.to_vm
    env = args.env

    # Load data
    registry = load_service_registry()
    postgres_clients = load_postgres_clients()
    topology = load_topology()
    known_guests = load_known_guests()

    # Validate inputs
    if svc_name not in registry:
        sys.exit(
            f"ERROR: '{svc_name}' not found in platform_service_registry.\n"
            f"  Check inventory/group_vars/all/platform_services.yml."
        )

    from_vm = registry[svc_name].get("host_group", "")
    if not from_vm:
        sys.exit(f"ERROR: '{svc_name}' has no host_group in platform_service_registry.")

    if to_vm == from_vm:
        print(f"No migration needed: {svc_name} is already on {to_vm}.")
        return 0

    if known_guests and to_vm not in known_guests:
        sys.exit(
            f"ERROR: Target VM '{to_vm}' is not in platform_guest_catalog.by_name.\n"
            f"  Known guests: {', '.join(sorted(known_guests))}"
        )

    # Print migration summary
    print(f"\nMIGRATION PLAN: {svc_name}  {from_vm} → {to_vm}  [env={env}]")
    print("─" * 70)

    dry_run = args.dry_run

    # --- Registry updates ---
    if dry_run:
        print("\n[Registry changes — would apply]")
        print(f"  platform_services.yml  {svc_name}.host_group: {from_vm} → {to_vm}")
        has_upstream = bool(registry.get(svc_name, {}).get("proxy", {}).get("upstream_host"))
        if has_upstream:
            print(f"  platform_services.yml  {svc_name}.proxy.upstream_host: {from_vm} → {to_vm}")
        if _has_topology_entry(svc_name, topology):
            print(f"  proxmox-host.yml      lv3_service_topology.{svc_name}: all refs {from_vm!r} → {to_vm!r}")
    else:
        print("\nApplying registry changes...")
        all_changes: list[str] = []
        all_changes.extend(update_platform_services(svc_name, from_vm, to_vm))
        all_changes.extend(update_proxmox_host_vars(svc_name, from_vm, to_vm))
        if all_changes:
            for c in all_changes:
                print(c)
        else:
            print("  (no changes applied — fields may already be correct)")

    # --- Converge plan ---
    steps = build_migration_plan(svc_name, from_vm, to_vm, registry, postgres_clients, topology)
    print(f"\nConverge sequence ({len(steps)} steps):")
    for i, step in enumerate(steps, 1):
        cmd = step.to_command(env) if step.make_target else ["validate_topology_consistency.py --check"]
        print(f"  {i}. {step.description}")
        print(f"     $ {' '.join(cmd)}")

    if dry_run:
        print("\n[dry-run complete — no files modified, no converges run]")
        print(f"  To execute: python scripts/migrate_service.py --svc {svc_name} --to {to_vm} --execute")
        return 0

    # --- Execute ---
    print("\nExecuting migration...")
    failed_step: str | None = None
    for step in steps:
        ok = run_step(step, env, dry_run=False)
        if not ok:
            failed_step = step.description
            break

    success = failed_step is None
    receipt_path = write_receipt(
        svc_name,
        from_vm,
        to_vm,
        all_changes,
        steps,
        env,
        success=success,
        failed_step=failed_step,
    )

    print(f"\n{'─' * 70}")
    if success:
        print(f"✓ Migration complete: {svc_name} is now on {to_vm}")
        print(f"  Receipt: {receipt_path.relative_to(REPO_ROOT)}")
        print("\nNext steps:")
        print("  1. Review registry changes: git diff")
        print(f"  2. Commit: git add inventory/ && git commit -m 'migrate {svc_name}: {from_vm} → {to_vm}'")
        print("  3. Push: git push origin main")
        if _uses_postgres(svc_name, postgres_clients):
            print("  4. Update versions/stack.yaml live-apply receipt for postgres_vm")
        return 0
    else:
        print(f"✗ Migration FAILED at step: {failed_step}")
        print(f"  Receipt: {receipt_path.relative_to(REPO_ROOT)}")
        print("\nRecovery:")
        print("  The registry files were already updated. If you need to roll back:")
        print("    git checkout -- inventory/group_vars/all/platform_services.yml")
        print("    git checkout -- inventory/host_vars/proxmox-host.yml")
        return 1


if __name__ == "__main__":
    sys.exit(main())
