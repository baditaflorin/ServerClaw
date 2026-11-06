"""Tests for config/0docker/dockerhost-pbs-relay: VM 100 reaches own-pbs :8007 through the 0docker hypervisor's direct tailnet path.

Text checks only (CI has no nft): the relay must stay as narrow as it is described, load only its own table, and rely on a tailnet grant that still exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "config" / "0docker" / "dockerhost-pbs-relay"
NFT = (DIR / "dockerhost-pbs-relay.nft").read_text()
UNIT = (DIR / "dockerhost-pbs-relay.service").read_text()
INSTALL = (DIR / "install-host.sh").read_text()
POLICY_PATH = REPO / "config" / "tailscale" / "policy.hujson"


def rules(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if re.match(r"^\s+(iifname|oifname)\b", l)]


def test_every_rule_matches_the_one_vm_and_the_one_port_and_nothing_is_published():
    found = rules(NFT)
    assert len(found) == 3, found
    for rule in found:
        assert "ip saddr 10.10.10.20 " in rule, rule  # only VM 100 may use the relay
        assert "tcp dport 8007" in rule, rule
    dnat = [r for r in found if "dnat to" in r]
    assert dnat == ['iifname "vmbr1" ip saddr 10.10.10.20 ip daddr 10.10.10.1 tcp dport 8007 counter dnat to 100.64.0.11:8007']
    masq = [r for r in found if "masquerade" in r]
    assert masq == ['oifname "tailscale0" ip saddr 10.10.10.20 ip daddr 100.64.0.11 tcp dport 8007 counter masquerade']
    assert any("maxseg" in r and 'oifname "tailscale0"' in r for r in found)
    code = "\n".join(l for l in NFT.splitlines() if not l.lstrip().startswith("#"))
    assert "enp5s0" not in code and "flush" not in code and "0.0.0.0" not in code and "10.10.10.0/24" not in code
    assert code.count("table ip dockerhost_pbs_relay") == 1 and "table inet" not in code


def test_the_unit_loads_and_removes_only_its_own_table():
    assert "Type=oneshot" in UNIT and "RemainAfterExit=yes" in UNIT
    assert "ExecStart=/usr/sbin/nft -f /etc/nftables/dockerhost-pbs-relay.nft" in UNIT
    assert "ExecStop=-/usr/sbin/nft delete table ip dockerhost_pbs_relay" in UNIT and "ExecStartPre=-/usr/sbin/nft delete table ip dockerhost_pbs_relay" in UNIT
    assert "flush" not in UNIT
    after = re.search(r"^After=(.*)$", UNIT, re.M).group(1)
    assert "tailscaled.service" in after and "fleet-lockdown.service" in after and "WantedBy=multi-user.target" in UNIT


def test_the_installer_validates_first_never_flushes_the_ruleset_and_can_undo_itself():
    assert "nft -c -f dockerhost-pbs-relay.nft" in INSTALL
    assert INSTALL.index("nft -c -f") < INSTALL.index("install -m 644 dockerhost-pbs-relay.nft")
    code = "\n".join(l for l in INSTALL.splitlines() if not l.lstrip().startswith("#"))
    assert "flush ruleset" not in code and "--undo" in code
    deletes = re.findall(r"nft delete table (\S+) (\S+)", code)
    assert deletes and all(t == ("ip", '"$TABLE"') for t in deletes)
    assert 'grep -q "dnat to 100.64.0.11:8007"' in INSTALL and 'bash "$0" --undo' in INSTALL


def test_the_hypervisors_tailnet_identity_still_has_the_grant_the_relay_depends_on():
    """The masqueraded traffic leaves as 100.64.0.5; without this grant (and its policy test) the relay would quietly stop working."""
    if not POLICY_PATH.exists():
        pytest.skip("deployment policy is intentionally excluded from the public mirror")
    grants = re.findall(r'\{\s*"src":\s*\[([^\]]*)\],\s*"dst":\s*\[([^\]]*)\],\s*"ip":\s*\[([^\]]*)\],?\s*\}', POLICY_PATH.read_text())
    ok = [g for g in grants if "100.64.0.5/32" in g[0] and "100.64.0.11/32" in g[1] and "tcp:8007" in g[2]]
    assert ok, "grant 100.64.0.5/32 -> 100.64.0.11/32 tcp:8007 is missing from config/tailscale/policy.hujson"


def test_the_backup_tool_uses_the_relay_and_the_fallback_is_the_same_server_over_the_tailnet():
    cfg = json.loads((REPO / "config" / "0docker" / "dockerhost-state-backup" / "config.json").read_text())
    assert cfg["repository"] == "backup-dockerhost@pbs!state@10.10.10.1:8007:own-pbs"
    readme = (DIR / "README.md").read_text()
    assert "100.64.0.11" in readme and "fallback" in readme.lower()
