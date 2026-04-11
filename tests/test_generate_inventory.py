"""Unit tests for scripts/generate_inventory.py.

Tests cover:
- build_inventory() pure function correctness
- IP derivation (from proxmox_guests[*].ipv4)
- Staging host generation (has_staging: true)
- Group membership (postgres_guests, backup_guests)
- Drift detection (--check mode)
- YAML serialisation round-trips
- Ansible dynamic inventory JSON (--list, --host)
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_inventory import (
    _net_prefix,
    ansible_host,
    ansible_list,
    build_inventory,
    check_drift,
    generate,
    render_yaml,
)


# ---------------------------------------------------------------------------
# Minimal fixture — mirrors real proxmox-host.yml structure
# ---------------------------------------------------------------------------

MINIMAL_HOST_VARS: dict = {
    "management_tailscale_ipv4": "100.64.0.1",
    "proxmox_staging_ipv4": "10.20.10.1",
    "proxmox_guests": [
        {
            "vmid": 110,
            "name": "nginx",
            "role": "nginx",
            "has_staging": True,
            "ipv4": "10.10.10.10",
            "tags": ["ingress", "nginx", "lv3"],
        },
        {
            "vmid": 120,
            "name": "docker-runtime",
            "role": "docker-runtime",
            "has_staging": True,
            "ipv4": "10.10.10.20",
            "tags": ["docker", "runtime", "lv3"],
        },
        {
            "vmid": 150,
            "name": "postgres",
            "role": "postgres",
            "has_staging": True,
            "ipv4": "10.10.10.50",
            "tags": ["postgres", "database", "lv3"],
        },
        {
            "vmid": 151,
            "name": "postgres-replica",
            "role": "postgres-replica",
            "has_staging": False,
            "ipv4": "10.10.10.51",
            "tags": ["postgres", "database", "ha", "lv3"],
        },
        {
            "vmid": 160,
            "name": "backup",
            "role": "backup",
            "has_staging": True,
            "ipv4": "10.10.10.60",
            "tags": ["backup", "pbs", "lv3"],
        },
        {
            "vmid": 192,
            "name": "runtime-control",
            "role": "runtime-control",
            # No has_staging — defaults to False
            "ipv4": "10.10.10.92",
            "tags": ["docker", "runtime", "control", "lv3"],
        },
    ],
}


# ---------------------------------------------------------------------------
# _net_prefix
# ---------------------------------------------------------------------------


def test_net_prefix_strips_last_octet() -> None:
    assert _net_prefix("10.10.10.1") == "10.10.10."
    assert _net_prefix("10.20.10.1") == "10.20.10."
    assert _net_prefix("192.168.1.254") == "192.168.1."


# ---------------------------------------------------------------------------
# build_inventory — production hosts
# ---------------------------------------------------------------------------


def test_all_production_guests_in_lv3_guests() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        assert g["name"] in lv3, f"Missing production guest: {g['name']}"


def test_production_guest_ansible_host_matches_ipv4() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        assert lv3[g["name"]]["ansible_host"] == g["ipv4"]


def test_production_deployment_environment() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        assert lv3[g["name"]]["deployment_environment"] == "production"


def test_production_group_contains_proxmox_host() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    assert "proxmox-host" in inv["all"]["children"]["production"]["hosts"]


def test_production_group_contains_all_guests() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    prod = inv["all"]["children"]["production"]["hosts"]
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        assert g["name"] in prod


# ---------------------------------------------------------------------------
# build_inventory — staging hosts
# ---------------------------------------------------------------------------


def test_staging_hosts_created_for_has_staging_guests() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    staging_guests = [g for g in MINIMAL_HOST_VARS["proxmox_guests"] if g.get("has_staging")]
    for g in staging_guests:
        sname = f"{g['name']}-staging"
        assert sname in lv3, f"Missing staging host: {sname}"


def test_staging_host_ip_uses_staging_prefix() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    staging_pfx = "10.20.10."
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        if not g.get("has_staging"):
            continue
        sname = f"{g['name']}-staging"
        expected_ip = staging_pfx + str(g["vmid"] % 100)
        assert lv3[sname]["ansible_host"] == expected_ip, (
            f"{sname}: expected {expected_ip}, got {lv3[sname]['ansible_host']}"
        )


def test_staging_host_vmid_formula() -> None:
    """VMID % 100 must equal last octet of the staging IP."""
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        if not g.get("has_staging"):
            continue
        sname = f"{g['name']}-staging"
        ip = lv3[sname]["ansible_host"]
        last_octet = int(ip.rsplit(".", 1)[-1])
        assert last_octet == g["vmid"] % 100, (
            f"{sname}: VMID {g['vmid']} % 100 = {g['vmid'] % 100}, but IP last octet is {last_octet}"
        )


def test_no_staging_host_without_has_staging() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    no_staging = [g for g in MINIMAL_HOST_VARS["proxmox_guests"] if not g.get("has_staging")]
    for g in no_staging:
        sname = f"{g['name']}-staging"
        assert sname not in lv3, f"Unexpected staging host: {sname}"


def test_staging_deployment_environment() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    for key, val in lv3.items():
        if key.endswith("-staging"):
            assert val["deployment_environment"] == "staging"


# ---------------------------------------------------------------------------
# build_inventory — group membership
# ---------------------------------------------------------------------------


def test_postgres_guests_derived_from_tags() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    pg = inv["all"]["children"]["postgres_guests"]["hosts"]
    # Production postgres guests
    assert "postgres" in pg
    assert "postgres-replica" in pg
    # Staging counterpart (postgres has has_staging: True)
    assert "postgres-staging" in pg
    # Non-postgres guests must not appear
    assert "nginx" not in pg
    assert "backup" not in pg


def test_backup_guests_derived_from_tags() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    bu = inv["all"]["children"]["backup_guests"]["hosts"]
    assert "backup" in bu
    assert "backup-staging" in bu
    assert "nginx" not in bu
    assert "postgres" not in bu


def test_proxmox_hosts_group_has_correct_ansible_host() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    ph = inv["all"]["children"]["proxmox_hosts"]["hosts"]["proxmox-host"]
    # Must contain the env var lookup with the Tailscale IP as default
    assert "LV3_PROXMOX_HOST_ADDR" in ph["ansible_host"]
    assert "100.64.0.1" in ph["ansible_host"]


def test_platform_group_has_required_children() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    children = inv["all"]["children"]["platform"]["children"]
    for grp in ("proxmox_hosts", "lv3_guests", "postgres_guests", "backup_guests"):
        assert grp in children


# ---------------------------------------------------------------------------
# YAML serialisation
# ---------------------------------------------------------------------------


def test_jinja2_strings_are_double_quoted() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    output = render_yaml(inv)
    # The env lookup in proxmox_hosts must appear double-quoted
    assert '"{{ lookup(' in output or '"{{ lookup(' in output


def test_ansible_host_patterns_are_quoted() -> None:
    inv = build_inventory(MINIMAL_HOST_VARS)
    output = render_yaml(inv)
    # :& patterns must be quoted so YAML doesn't treat & as anchor
    assert '"proxmox_hosts:&production"' in output or "proxmox_hosts:&production" not in output.replace('"', "")


def test_yaml_round_trip() -> None:
    """Generated YAML must parse back to the same structure."""
    inv = build_inventory(MINIMAL_HOST_VARS)
    output = render_yaml(inv)
    parsed = yaml.safe_load(output)
    # Check key structural elements survived the round-trip
    assert "all" in parsed
    assert "lv3_guests" in parsed["all"]["children"]
    lv3 = parsed["all"]["children"]["lv3_guests"]["hosts"]
    assert "nginx" in lv3
    assert lv3["nginx"]["ansible_host"] == "10.10.10.10"


# ---------------------------------------------------------------------------
# Ansible dynamic inventory
# ---------------------------------------------------------------------------


def test_ansible_list_contains_all_hosts() -> None:
    result = ansible_list(MINIMAL_HOST_VARS)
    hostvars = result["_meta"]["hostvars"]
    assert "proxmox-host" in hostvars
    for g in MINIMAL_HOST_VARS["proxmox_guests"]:
        assert g["name"] in hostvars


def test_ansible_list_contains_staging_hosts() -> None:
    result = ansible_list(MINIMAL_HOST_VARS)
    hostvars = result["_meta"]["hostvars"]
    assert "nginx-staging" in hostvars
    assert "postgres-staging" in hostvars
    assert "backup-staging" in hostvars


def test_ansible_host_returns_hostvars() -> None:
    result = ansible_host(MINIMAL_HOST_VARS, "nginx")
    assert result["ansible_host"] == "10.10.10.10"


def test_ansible_host_unknown_returns_empty() -> None:
    result = ansible_host(MINIMAL_HOST_VARS, "does-not-exist")
    assert result == {}


# ---------------------------------------------------------------------------
# generate() and drift detection
# ---------------------------------------------------------------------------


def test_generate_includes_header() -> None:
    output = generate(MINIMAL_HOST_VARS)
    assert "GENERATED" in output
    assert "make generate-inventory" in output


def test_check_drift_detects_mismatch(tmp_path: Path) -> None:
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# stale content\nall: {}\n")
    assert not check_drift(MINIMAL_HOST_VARS, current_path=hosts_yml)


def test_check_drift_passes_when_current(tmp_path: Path) -> None:
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text(generate(MINIMAL_HOST_VARS))
    assert check_drift(MINIMAL_HOST_VARS, current_path=hosts_yml)


def test_check_drift_fails_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "hosts.yml"
    assert not check_drift(MINIMAL_HOST_VARS, current_path=missing)


# ---------------------------------------------------------------------------
# Real proxmox-host.yml integration smoke test
# ---------------------------------------------------------------------------

REAL_HOST_VARS_PATH = Path(__file__).resolve().parents[1] / "inventory" / "host_vars" / "proxmox-host.yml"


@pytest.mark.skipif(
    not REAL_HOST_VARS_PATH.exists(),
    reason="Real proxmox-host.yml not available",
)
def test_real_host_vars_vmid_formula() -> None:
    """For every real production guest, VMID % 100 == last octet of ipv4."""
    with REAL_HOST_VARS_PATH.open() as fh:
        host_vars = yaml.safe_load(fh)
    for g in host_vars.get("proxmox_guests", []):
        vmid = int(g["vmid"])
        ipv4 = g["ipv4"]
        last_octet = int(ipv4.rsplit(".", 1)[-1])
        assert last_octet == vmid % 100, (
            f"VMID {vmid} ({g['name']}): expected last octet {vmid % 100}, got {last_octet} from {ipv4}"
        )


@pytest.mark.skipif(
    not REAL_HOST_VARS_PATH.exists(),
    reason="Real proxmox-host.yml not available",
)
def test_real_host_vars_generates_17_production_guests() -> None:
    with REAL_HOST_VARS_PATH.open() as fh:
        host_vars = yaml.safe_load(fh)
    inv = build_inventory(host_vars)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    production = [k for k, v in lv3.items() if isinstance(v, dict) and v.get("deployment_environment") == "production"]
    assert len(production) == 17, f"Expected 17 production guests, got {len(production)}: {production}"


@pytest.mark.skipif(
    not REAL_HOST_VARS_PATH.exists(),
    reason="Real proxmox-host.yml not available",
)
def test_real_host_vars_generates_7_staging_guests() -> None:
    with REAL_HOST_VARS_PATH.open() as fh:
        host_vars = yaml.safe_load(fh)
    inv = build_inventory(host_vars)
    lv3 = inv["all"]["children"]["lv3_guests"]["hosts"]
    staging = [k for k, v in lv3.items() if isinstance(v, dict) and v.get("deployment_environment") == "staging"]
    assert len(staging) == 7, f"Expected 7 staging guests, got {len(staging)}: {staging}"


@pytest.mark.skipif(
    not REAL_HOST_VARS_PATH.exists(),
    reason="Real proxmox-host.yml not available",
)
def test_real_hosts_yml_not_drifted() -> None:
    """Fail if inventory/hosts.yml is out of sync with proxmox-host.yml."""
    with REAL_HOST_VARS_PATH.open() as fh:
        host_vars = yaml.safe_load(fh)
    hosts_yml = REAL_HOST_VARS_PATH.parents[1] / "hosts.yml"
    assert check_drift(host_vars, current_path=hosts_yml), (
        "inventory/hosts.yml is out of sync with proxmox_guests. Run: make generate-inventory"
    )
