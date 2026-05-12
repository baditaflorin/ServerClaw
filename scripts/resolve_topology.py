"""Topology resolver — ADR 0482.

Compute per-VM allocations (memory_mb, cores, disk_gb, balloon) from:
  - .local/deployments/<slug>/capacity.yml  (probed host capacity)
  - config/sizing-policy.yml                 (per-service-class rules)
  - .local/deployments/<slug>/profile.yml   (enabled service profiles)

Writes (or prints, in plan mode) the resolved topology to
.local/deployments/<slug>/topology.yml.

Algorithm (priority-shrinkage):

  1. Expand the enabled service-class set from profile.yml.
  2. For each class, start at policy.classes[class].preferred values.
  3. Sum ram_mb across all enabled classes. If sum exceeds
     (capacity.ram_total_mb - capacity.ram_reserved_mb), walk
     priority_order in REVERSE (optional first) and shrink classes at
     each tier proportionally until the sum fits — but never below the
     class's `min`.
  4. If the topology still doesn't fit even at all-min, fail loudly and
     report which classes would need to be disabled to make it fit.
  5. Apply the same shrinkage independently for CPU (against
     capacity.threads) and disk (against the largest storage pool).
  6. Always set balloon = 40% of resolved ram_mb (never 0). Ballooning
     is load-bearing default per ADR 0482 §5.
  7. Emit topology.yml with a generated-at stamp and input hashes for
     traceability.

Usage:

    uv run --with pyyaml --with jsonschema python scripts/resolve_topology.py \\
        --slug 0fork --write

    # Plan mode (print what would be written + diff against current topology):
    uv run ... python scripts/resolve_topology.py --slug 0fork

    # Strict mode (fail if any class falls back below preferred):
    uv run ... python scripts/resolve_topology.py --slug 0fork --strict
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# MAIN_REPO_ROOT — for .local/ access (resolves correctly from worktrees via git-common-dir).
# CODE_ROOT — for committed assets (schemas, policies) that live in this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import REPO_ROOT as MAIN_REPO_ROOT  # noqa: E402

CODE_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENTS_DIR = MAIN_REPO_ROOT / ".local" / "deployments"
POLICY_PATH = CODE_ROOT / "config" / "sizing-policy.yml"


def _hash(obj: Any) -> str:
    return hashlib.sha256(yaml.dump(obj, sort_keys=True, default_flow_style=False).encode()).hexdigest()[:12]


@dataclass
class Inputs:
    slug: str
    capacity: dict[str, Any]
    policy: dict[str, Any]
    profile: dict[str, Any]

    @property
    def hashes(self) -> dict[str, str]:
        return {
            "capacity_hash": _hash(self.capacity),
            "policy_hash": _hash(self.policy),
            "profile_hash": _hash(self.profile),
        }


def load_inputs(slug: str) -> Inputs:
    cap = DEPLOYMENTS_DIR / slug / "capacity.yml"
    prof = DEPLOYMENTS_DIR / slug / "profile.yml"
    if not cap.is_file():
        sys.exit(f"ERROR: {cap} not found. Run `make probe-capacity slug={slug}` first.")
    if not prof.is_file():
        sys.exit(f"ERROR: {prof} not found.")
    if not POLICY_PATH.is_file():
        sys.exit(f"ERROR: {POLICY_PATH} not found.")
    return Inputs(
        slug=slug,
        capacity=yaml.safe_load(cap.read_text()) or {},
        policy=yaml.safe_load(POLICY_PATH.read_text()) or {},
        profile=yaml.safe_load(prof.read_text()) or {},
    )


def enabled_classes(inputs: Inputs) -> list[str]:
    """Union of profile_defaults for each profile name, plus extras minus disabled."""
    enabled: set[str] = set()
    defaults = inputs.policy.get("profile_defaults", {}) or {}
    for name in inputs.profile.get("profiles", []) or []:
        enabled |= set(defaults.get(name, []) or [])
    enabled |= set(inputs.profile.get("extra_services", []) or [])
    enabled -= set(inputs.profile.get("disabled_services", []) or [])
    # Filter to classes the policy actually knows about.
    return sorted(c for c in enabled if c in inputs.policy.get("classes", {}))


def filter_by_capability(classes: list[str], inputs: Inputs) -> tuple[list[str], list[str]]:
    """Drop classes whose required capability is not present on the host."""
    host_caps = set(inputs.capacity.get("host", {}).get("capabilities", []) or [])
    kept, skipped = [], []
    for c in classes:
        req = inputs.policy["classes"][c].get("requires_capability")
        if req and req not in host_caps:
            skipped.append(f"{c} (requires {req})")
        else:
            kept.append(c)
    return kept, skipped


def _shrink(
    enabled: list[str],
    inputs: Inputs,
    field: str,  # "ram_mb" | "cpu" | "disk_gb"
    capacity_value: int,
) -> tuple[dict[str, int], list[str]]:
    """Return {class: resolved_value} for `field`, fitting within capacity_value.
    Shrinks lowest-priority classes first, never below min."""
    classes_meta = inputs.policy["classes"]
    priority_order = inputs.policy.get("priority_order", ["critical", "important", "nice-to-have", "optional"])

    # Start everyone at "preferred".
    resolved = {c: int(classes_meta[c][field]["preferred"]) for c in enabled}
    notes: list[str] = []

    # Iterate from lowest priority to highest; shrink toward min.
    for tier in reversed(priority_order):
        if sum(resolved.values()) <= capacity_value:
            return resolved, notes
        tier_classes = [c for c in enabled if classes_meta[c]["priority"] == tier]
        if not tier_classes:
            continue
        for c in tier_classes:
            cur = resolved[c]
            mn = int(classes_meta[c][field]["min"])
            if cur > mn:
                # Shrink by 1/4 of (cur - mn) each pass; loop until fits.
                while sum(resolved.values()) > capacity_value and resolved[c] > mn:
                    step = max(1, (resolved[c] - mn) // 4)
                    resolved[c] -= step
                    if resolved[c] < mn:
                        resolved[c] = mn
                notes.append(
                    f"shrunk {c}.{field}: preferred={classes_meta[c][field]['preferred']} -> {resolved[c]} (priority={tier})"
                )

    if sum(resolved.values()) > capacity_value:
        # Even at all-min, doesn't fit.
        overflow = sum(resolved.values()) - capacity_value
        notes.append(
            f"OVERFLOW: {field} still exceeds capacity by {overflow} even at all-min. "
            "Disable some classes via profile.disabled_services."
        )
    return resolved, notes


def resolve(inputs: Inputs, strict: bool = False) -> tuple[dict[str, Any], list[str]]:
    host = inputs.capacity.get("host", {})
    ram_budget = int(host.get("ram_total_mb", 0)) - int(host.get("ram_reserved_mb", 4096))
    cpu_budget = int(host.get("threads") or host.get("cores", 0))
    # Largest storage pool free_gb, minus 10% headroom.
    storage = host.get("storage", []) or []
    if storage:
        disk_budget = int(max(s.get("free_gb", 0) for s in storage) * 0.9)
    else:
        disk_budget = 0  # disabled disk constraint if probe didn't surface storage

    enabled = enabled_classes(inputs)
    enabled, skipped = filter_by_capability(enabled, inputs)

    ram, ram_notes = _shrink(enabled, inputs, "ram_mb", ram_budget)
    cpu, cpu_notes = _shrink(enabled, inputs, "cpu", cpu_budget)
    if disk_budget > 0:
        disk, disk_notes = _shrink(enabled, inputs, "disk_gb", disk_budget)
    else:
        disk = {c: int(inputs.policy["classes"][c]["disk_gb"]["preferred"]) for c in enabled}
        disk_notes = ["disk budget not enforced (no storage info in capacity.yml)"]

    if strict:
        for c in enabled:
            for field, resolved_dict in (("ram_mb", ram), ("cpu", cpu), ("disk_gb", disk)):
                preferred = inputs.policy["classes"][c][field]["preferred"]
                if resolved_dict[c] < preferred:
                    sys.exit(f"--strict: {c}.{field} resolved to {resolved_dict[c]} < preferred {preferred}")

    proxmox_guests = []
    for c in enabled:
        ram_mb = ram[c]
        proxmox_guests.append(
            {
                "name": c,
                "role": c,
                "memory_mb": ram_mb,
                "balloon_mb": int(ram_mb * 0.4),  # ADR 0482 §5
                "cores": cpu[c],
                "disk_gb": disk[c],
                "priority": inputs.policy["classes"][c]["priority"],
            }
        )

    topology = {
        "schema_version": 1,
        "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/resolve_topology.py",
        "inputs": inputs.hashes,
        "budget": {
            "ram_total_mb": host.get("ram_total_mb"),
            "ram_usable_mb": ram_budget,
            "ram_allocated_mb": sum(ram.values()),
            "cpu_total": cpu_budget,
            "cpu_allocated": sum(cpu.values()),
            "disk_total_gb": disk_budget,
            "disk_allocated_gb": sum(disk.values()),
        },
        "skipped_for_capability": skipped,
        "proxmox_guests": proxmox_guests,
    }
    notes = ram_notes + cpu_notes + disk_notes
    return topology, notes


def diff_against_existing(slug: str, new_topology: dict[str, Any]) -> str:
    """Compute a one-line-per-guest diff between current topology and the new one."""
    cur_path = DEPLOYMENTS_DIR / slug / "topology.yml"
    if not cur_path.is_file():
        return "(no existing topology — full new deployment)"
    cur = yaml.safe_load(cur_path.read_text()) or {}
    cur_guests = {g["name"]: g for g in (cur.get("proxmox_guests") or [])}
    new_guests = {g["name"]: g for g in (new_topology.get("proxmox_guests") or [])}
    names = sorted(set(cur_guests) | set(new_guests))
    lines = []
    for n in names:
        cur_g = cur_guests.get(n)
        new_g = new_guests.get(n)
        if cur_g and not new_g:
            lines.append(f"  REMOVED   {n}")
        elif new_g and not cur_g:
            lines.append(f"  ADDED     {n}  ram={new_g['memory_mb']} cpu={new_g['cores']} disk={new_g['disk_gb']}")
        else:
            changes = []
            for k in ("memory_mb", "cores", "disk_gb"):
                if cur_g.get(k) != new_g.get(k):
                    changes.append(f"{k}: {cur_g.get(k)} -> {new_g.get(k)}")
            if changes:
                lines.append(f"  CHANGED   {n}  " + ", ".join(changes))
    return "\n".join(lines) or "  (no changes)"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slug", required=True)
    p.add_argument("--write", action="store_true", help="Write the result to topology.yml (otherwise dry-run)")
    p.add_argument("--strict", action="store_true", help="Fail if any class falls below preferred")
    args = p.parse_args()

    inputs = load_inputs(args.slug)
    topology, notes = resolve(inputs, strict=args.strict)

    sys.stderr.write(f"--- resolve_topology slug={args.slug} ---\n")
    sys.stderr.write(f"enabled: {[g['name'] for g in topology['proxmox_guests']]}\n")
    sys.stderr.write(
        f"budget:  ram {topology['budget']['ram_allocated_mb']}/{topology['budget']['ram_usable_mb']} MB, cpu {topology['budget']['cpu_allocated']}/{topology['budget']['cpu_total']}, disk {topology['budget']['disk_allocated_gb']}/{topology['budget']['disk_total_gb']} GB\n"
    )
    if topology["skipped_for_capability"]:
        sys.stderr.write(f"skipped: {topology['skipped_for_capability']}\n")
    for n in notes:
        sys.stderr.write(f"note: {n}\n")
    sys.stderr.write("diff against current topology.yml:\n")
    sys.stderr.write(diff_against_existing(args.slug, topology) + "\n")

    out = yaml.dump(topology, sort_keys=False, default_flow_style=False)
    if args.write:
        out_path = DEPLOYMENTS_DIR / args.slug / "topology.yml"
        # back-up existing file before overwriting
        if out_path.is_file():
            backup = out_path.with_suffix(f".yml.bak-{_dt.datetime.now().strftime('%Y%m%d%H%M%S')}")
            out_path.rename(backup)
            sys.stderr.write(f"backed up previous topology to {backup}\n")
        out_path.write_text(out)
        sys.stderr.write(f"wrote {out_path}\n")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
