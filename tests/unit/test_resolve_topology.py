"""Unit tests for scripts/resolve_topology.py — ADR 0482.

Covers:
  * determinism: same inputs produce same output (hashes match)
  * preferred allocation when host has headroom
  * priority-shrinkage when host is over-committed
  * capability gating (skip classes requiring missing host caps)
  * overflow detection (all-min still exceeds → note logged)
  * empty profile → empty topology
  * --strict mode raises when any class falls below preferred

The resolver is exercised in-process by calling resolve(Inputs(...))
directly with synthetic dicts — no IO, no SSH, no file system writes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("resolve_topology", SCRIPTS_DIR / "resolve_topology.py")
resolve_mod = importlib.util.module_from_spec(spec)
sys.modules["resolve_topology"] = resolve_mod  # dataclass introspection needs this
assert spec.loader is not None
spec.loader.exec_module(resolve_mod)
Inputs = resolve_mod.Inputs
resolve = resolve_mod.resolve
enabled_classes = resolve_mod.enabled_classes


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def base_policy() -> dict:
    """A small four-class policy spanning each priority tier."""
    return {
        "schema_version": 1,
        "priority_order": ["critical", "important", "nice-to-have", "optional"],
        "classes": {
            "nginx": {
                "priority": "critical",
                "cpu": {"min": 1, "preferred": 2, "max": 4},
                "ram_mb": {"min": 1024, "preferred": 4096, "max": 8192},
                "disk_gb": {"min": 16, "preferred": 32, "max": 64},
            },
            "monitoring": {
                "priority": "important",
                "cpu": {"min": 1, "preferred": 2, "max": 4},
                "ram_mb": {"min": 1024, "preferred": 4096, "max": 8192},
                "disk_gb": {"min": 16, "preferred": 32, "max": 64},
            },
            "backup": {
                "priority": "nice-to-have",
                "cpu": {"min": 1, "preferred": 2, "max": 4},
                "ram_mb": {"min": 1024, "preferred": 4096, "max": 8192},
                "disk_gb": {"min": 16, "preferred": 64, "max": 128},
            },
            "runtime-ai": {
                "priority": "optional",
                "requires_capability": "gpu",
                "cpu": {"min": 4, "preferred": 6, "max": 8},
                "ram_mb": {"min": 8192, "preferred": 16384, "max": 32768},
                "disk_gb": {"min": 32, "preferred": 64, "max": 128},
            },
        },
        "profile_defaults": {
            "core": ["nginx", "monitoring"],
            "full": ["nginx", "monitoring", "backup", "runtime-ai"],
        },
    }


def make_inputs(
    *,
    ram_mb: int = 32768,
    threads: int = 16,
    free_gb: int = 1000,
    profiles: list[str] | None = None,
    capabilities: list[str] | None = None,
    extras: list[str] | None = None,
    disabled: list[str] | None = None,
    policy: dict | None = None,
) -> "Inputs":
    return Inputs(
        slug="test",
        capacity={
            "schema_version": 1,
            "probed_via": "operator",
            "host": {
                "ram_total_mb": ram_mb,
                "ram_reserved_mb": 0,
                "cores": threads // 2,
                "threads": threads,
                "storage": [{"name": "local", "type": "zfs", "total_gb": free_gb, "free_gb": free_gb}],
                "capabilities": list(capabilities) if capabilities is not None else [],
            },
        },
        policy=policy if policy is not None else {},
        profile={
            "profiles": list(profiles) if profiles is not None else ["core"],
            "extra_services": list(extras) if extras is not None else [],
            "disabled_services": list(disabled) if disabled is not None else [],
            "service_overrides": {},
        },
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_empty_profile_produces_empty_topology(base_policy):
    inputs = make_inputs(profiles=[], policy=base_policy)
    topology, notes = resolve(inputs)
    assert topology["proxmox_guests"] == []
    assert topology["budget"]["ram_allocated_mb"] == 0


def test_core_profile_at_preferred_when_room_to_spare(base_policy):
    inputs = make_inputs(ram_mb=65536, threads=32, profiles=["core"], policy=base_policy)
    topology, _ = resolve(inputs)
    names = {g["name"]: g for g in topology["proxmox_guests"]}
    assert set(names) == {"nginx", "monitoring"}
    # Should land at preferred (no shrink needed).
    assert names["nginx"]["memory_mb"] == 4096
    assert names["monitoring"]["memory_mb"] == 4096
    assert names["nginx"]["cores"] == 2


def test_always_on_ballooning_default(base_policy):
    """ADR 0482 §5: every guest must get balloon_mb ≈ 40% of memory_mb."""
    inputs = make_inputs(ram_mb=65536, threads=32, profiles=["core"], policy=base_policy)
    topology, _ = resolve(inputs)
    for g in topology["proxmox_guests"]:
        assert g["balloon_mb"] > 0, f"balloon disabled on {g['name']}"
        assert g["balloon_mb"] == int(g["memory_mb"] * 0.4), f"wrong balloon ratio on {g['name']}"


def test_priority_shrinkage_targets_lowest_priority_first(base_policy):
    """nice-to-have shrinks before important shrinks before critical."""
    # A moderately tight host where 'full' profile fits with priority shrinkage
    # but critical classes can stay at preferred. Pick budget large enough that
    # shrinking optional + nice-to-have alone is sufficient.
    # preferred total: 4096 (nginx-crit) + 4096 (mon-imp) + 4096 (backup-nh) + 16384 (ai-opt) = 28672 MB
    # mins:  1024 + 1024 + 1024 + 8192 = 11264
    # Budget at 22528 forces opt+nh to shrink, but important+critical can stay preferred.
    inputs = make_inputs(
        ram_mb=22528,
        threads=32,
        profiles=["full"],
        capabilities=["gpu"],  # so runtime-ai is enabled
        policy=base_policy,
    )
    topology, _notes = resolve(inputs)
    by_name = {g["name"]: g for g in topology["proxmox_guests"]}
    # critical stays at preferred (lowest priorities absorbed the cut).
    assert by_name["nginx"]["memory_mb"] == 4096
    # important also stayed at preferred.
    assert by_name["monitoring"]["memory_mb"] == 4096
    # optional shrank.
    assert by_name["runtime-ai"]["memory_mb"] < 16384
    # nice-to-have shrank too (or stayed at preferred if optional absorbed enough).
    # In any case, optional must have shrunk at least as much as nice-to-have.
    optional_drop = 16384 - by_name["runtime-ai"]["memory_mb"]
    nh_drop = 4096 - by_name["backup"]["memory_mb"]
    assert optional_drop >= nh_drop, "optional should shrink at least as much as nice-to-have"
    # Sum fits.
    assert sum(g["memory_mb"] for g in topology["proxmox_guests"]) <= 22528


def test_critical_shrinks_only_after_lower_priorities_at_min(base_policy):
    """ADR 0482: critical is shrunk only when nice-to-have + optional + important are at min."""
    # Force severe pressure where everything must shrink toward min.
    # mins total = 11264. Budget 11500 leaves only ~236 MB headroom -> nearly all-min.
    inputs = make_inputs(
        ram_mb=11500,
        threads=32,
        profiles=["full"],
        capabilities=["gpu"],
        policy=base_policy,
    )
    topology, _ = resolve(inputs)
    by = {g["name"]: g["memory_mb"] for g in topology["proxmox_guests"]}
    # Every non-critical class should have shrunk close to min.
    assert by["runtime-ai"] == 8192  # at min
    assert by["backup"] == 1024  # at min
    assert by["monitoring"] == 1024  # at min
    # critical may or may not have shrunk slightly, but never below min.
    assert by["nginx"] >= 1024


def test_capability_gating_skips_classes_without_required_host_cap(base_policy):
    """runtime-ai requires gpu; host without gpu skips it."""
    inputs = make_inputs(
        ram_mb=65536,
        threads=32,
        profiles=["full"],
        capabilities=[],  # no gpu
        policy=base_policy,
    )
    topology, _ = resolve(inputs)
    names = {g["name"] for g in topology["proxmox_guests"]}
    assert "runtime-ai" not in names
    assert any("runtime-ai" in s for s in topology["skipped_for_capability"])


def test_capability_gating_includes_when_cap_present(base_policy):
    inputs = make_inputs(
        ram_mb=65536,
        threads=32,
        profiles=["full"],
        capabilities=["gpu"],
        policy=base_policy,
    )
    topology, _ = resolve(inputs)
    names = {g["name"] for g in topology["proxmox_guests"]}
    assert "runtime-ai" in names


def test_overflow_detection_notes_when_all_min_still_exceeds(base_policy):
    """When even all-min exceeds host RAM, an OVERFLOW note is emitted."""
    # min total for full+gpu = 1024+1024+1024+8192 = 11264.
    # Give it 4 GB so even all-min can't fit.
    inputs = make_inputs(
        ram_mb=4096,
        threads=32,
        profiles=["full"],
        capabilities=["gpu"],
        policy=base_policy,
    )
    _topology, notes = resolve(inputs)
    overflow_note = next((n for n in notes if "OVERFLOW" in n and "ram_mb" in n), None)
    assert overflow_note is not None, f"expected OVERFLOW note for ram_mb, got notes: {notes}"


def test_determinism_same_inputs_same_hash(base_policy):
    """Two resolves with identical inputs produce identical content + hashes."""
    a = make_inputs(ram_mb=32768, threads=16, profiles=["core"], policy=base_policy)
    b = make_inputs(ram_mb=32768, threads=16, profiles=["core"], policy=base_policy)
    ta, _ = resolve(a)
    tb, _ = resolve(b)
    assert ta["inputs"]["capacity_hash"] == tb["inputs"]["capacity_hash"]
    assert ta["inputs"]["policy_hash"] == tb["inputs"]["policy_hash"]
    assert ta["inputs"]["profile_hash"] == tb["inputs"]["profile_hash"]
    assert ta["proxmox_guests"] == tb["proxmox_guests"]


def test_extras_and_disabled_compose_correctly(base_policy):
    """profile.extras adds, disabled subtracts — even when in the default set."""
    inputs = make_inputs(
        ram_mb=65536,
        threads=32,
        profiles=["core"],  # nginx + monitoring
        extras=["backup"],  # +backup
        disabled=["monitoring"],  # -monitoring
        policy=base_policy,
    )
    enabled = enabled_classes(inputs)
    assert set(enabled) == {"nginx", "backup"}


def test_strict_mode_raises_when_below_preferred(base_policy):
    """--strict surfaces any shrinkage as a SystemExit."""
    inputs = make_inputs(
        ram_mb=4096,
        threads=32,
        profiles=["core"],
        policy=base_policy,
    )
    with pytest.raises(SystemExit):
        resolve(inputs, strict=True)


def test_strict_mode_silent_when_all_at_preferred(base_policy):
    """--strict happy path: no shrinkage means no exit."""
    inputs = make_inputs(
        ram_mb=65536,
        threads=32,
        profiles=["core"],
        policy=base_policy,
    )
    # Must not raise.
    topology, _ = resolve(inputs, strict=True)
    assert topology["proxmox_guests"]


def test_budget_accounting_is_consistent(base_policy):
    """Sum of guest allocations matches the reported budget totals."""
    inputs = make_inputs(ram_mb=32768, threads=16, profiles=["core"], policy=base_policy)
    topology, _ = resolve(inputs)
    sum_ram = sum(g["memory_mb"] for g in topology["proxmox_guests"])
    sum_cpu = sum(g["cores"] for g in topology["proxmox_guests"])
    sum_disk = sum(g["disk_gb"] for g in topology["proxmox_guests"])
    assert topology["budget"]["ram_allocated_mb"] == sum_ram
    assert topology["budget"]["cpu_allocated"] == sum_cpu
    assert topology["budget"]["disk_allocated_gb"] == sum_disk
