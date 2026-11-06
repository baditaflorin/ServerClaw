"""No guest address may equal a keepalived VIP, the VIPs are distinct, and the network policy never names a VIP as a VM or a VRRP peer.

On 2026-10-29 the agent-history guest (vmid 155) was given 10.10.10.55, which `postgres_ha.vip_ipv4` already declared as the Postgres
HA VIP (since 2026-08-27). The VIP was never deployed, so nothing broke; the first Patroni/keepalived deploy would have put two hosts
on one address, and the service topology (`postgres.private_ip: {{ postgres_ha.vip_ipv4 }}`) would have pointed the database name at
the store. These tests keep that from recurring, in the live inventory and in the public fork template.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
INVENTORIES = [
    REPO / "inventory" / "host_vars" / "proxmox-host.yml",
    REPO / "publication" / "templates" / "proxmox-host.yml",
]
NETWORK_POLICY = REPO / "config" / "network-policy" / "0mcp.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _vips(host_vars: dict) -> dict[str, str]:
    return {
        name: str(block["vip_ipv4"])
        for name, block in host_vars.items()
        if isinstance(block, dict) and "vip_ipv4" in block
    }


def _guest_addresses(host_vars: dict) -> dict[str, str]:
    return {guest["name"]: str(guest["ipv4"]) for guest in host_vars["proxmox_guests"]}


@pytest.mark.parametrize("path", INVENTORIES, ids=lambda p: p.parent.parent.name)
def test_every_ha_vip_is_declared_and_distinct(path: Path) -> None:
    vips = _vips(_load(path))
    assert vips, "the inventory declares at least one *_ha block with a vip_ipv4"
    duplicates = [address for address, count in Counter(vips.values()).items() if count > 1]
    assert not duplicates, f"two HA clusters share a VIP: {duplicates} ({vips})"


@pytest.mark.parametrize("path", INVENTORIES, ids=lambda p: p.parent.parent.name)
def test_no_guest_address_equals_a_vip_or_another_guest(path: Path) -> None:
    host_vars = _load(path)
    guests = _guest_addresses(host_vars)
    vips = _vips(host_vars)
    clashes = {name: address for name, address in guests.items() if address in set(vips.values())}
    assert not clashes, f"a guest sits on a keepalived VIP: {clashes} (VIPs: {vips})"
    twice = [address for address, count in Counter(guests.values()).items() if count > 1]
    assert not twice, f"two guests share an address: {twice}"
    assert str(host_vars["proxmox_internal_ipv4"]) not in set(vips.values()) | set(guests.values())


def test_the_network_policy_never_names_a_vip_as_a_vm_or_a_vrrp_peer() -> None:
    vips = set(_vips(_load(INVENTORIES[0])).values())
    policy = _load(NETWORK_POLICY)
    for vmid, vm in policy["vms"].items():
        assert str(vm["ip"]) not in vips, f"VM {vmid} ({vm['name']}) has a VIP as its address"
        for group in vm.get("groups", []):
            if group.get("proto") == "vrrp":
                named = {str(source) for source in group["from"]}
                assert not named & vips, f"VM {vmid}: a VRRP group names a VIP instead of its peer: {named & vips}"


def test_the_postgres_vip_is_not_the_store_address() -> None:
    host_vars = _load(INVENTORIES[0])
    assert _vips(host_vars)["postgres_ha"] != _guest_addresses(host_vars)["agent-history"]
