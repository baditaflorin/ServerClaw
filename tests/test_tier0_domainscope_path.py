"""The DomainScope standby's network path has three parts that live in three places and must stay in step:

  1. the tailnet grant (config/tailscale/policy.hujson): standby edge -> the 0infer hypervisor, exactly two ports
  2. the hypervisor's nft DNAT (config/0infer/tier0-runner/host/infer-domainscope-standby.nft): those two ports from the edge's address -> VM 8101
  3. the standby edge's gateway build (config/0infer/tier0-runner/gateway-extra.json): the DomainScope vhost's private upstreams -> the hypervisor's tailnet address, same ports

Editing one without the others leaves a standby edge that answers 502 during a real failover and passes every other check, so this test ties them together
and keeps each of them as narrow as it was reviewed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import tailscale_policy_sync as tps  # noqa: E402

NFT = (REPO / "config/0infer/tier0-runner/host/infer-domainscope-standby.nft").read_text()
EXTRA = json.loads((REPO / "config/0infer/tier0-runner/gateway-extra.json").read_text())
POLICY_PATH = REPO / "config/tailscale/policy.hujson"

EDGE, HOST, VM8101 = "100.84.241.55", "100.64.0.21", "10.70.10.50"
PORTS = {23480, 23481}


@pytest.fixture
def deployment_policy():
    if not POLICY_PATH.exists():
        pytest.skip("deployment policy is intentionally excluded from the public mirror")
    return tps.parse_hujson(POLICY_PATH.read_text())


def rules():
    """The non-comment rule lines of the nft file."""
    return [l.strip() for l in NFT.splitlines() if l.strip() and not l.strip().startswith("#")]


def dnat_rules():
    return [r for r in rules() if "dnat to" in r]


def test_nft_is_one_dnat_rule_from_one_address_to_one_vm_on_two_ports():
    body = "\n".join(r for r in rules() if not r.startswith("type "))              # the chain declaration says `policy accept`; everything else is a rule
    assert len(dnat_rules()) == 1
    r = dnat_rules()[0]
    assert f"ip saddr {EDGE}" in r and f"ip daddr {HOST}" in r and r.endswith(f"dnat to {VM8101}")
    assert 'iifname "tailscale0"' in r                                              # only what arrives over the tailnet
    ports = set(map(int, re.search(r"tcp dport \{([^}]*)\}", r).group(1).replace(" ", "").split(",")))
    assert ports == PORTS
    for forbidden in ("masquerade", "snat", "forward", "accept", "drop", "udp", "daddr 0.0.0.0", "/16", "/8"):
        assert forbidden not in body, forbidden                                     # nothing that widens it or touches other traffic
    assert "type nat hook prerouting priority dstnat; policy accept;" in rules()   # a nat prerouting chain that never drops


def test_the_tailnet_grant_covers_exactly_the_nft_rule(deployment_policy):
    grants = [g for g in deployment_policy["grants"] if g.get("dst") == [f"{HOST}/32"] and set(g.get("ip", [])) == {f"tcp:{p}" for p in PORTS}]
    assert len(grants) == 1, "the grant for the standby edge -> hypervisor web ports must exist exactly once"
    g = grants[0]
    assert f"{EDGE}/32" in g["src"] and set(g["src"]) <= {f"{EDGE}/32", "tag:edge-standby"}   # the edge, by address and by tag, nobody else


def test_the_policy_tests_prove_the_grant_and_its_limits(deployment_policy):
    accepts = {(t["src"], a) for t in deployment_policy["tests"] for a in t.get("accept", []) if t.get("proto", "tcp") == "tcp"}
    denies = {(t["src"], d) for t in deployment_policy["tests"] for d in t.get("deny", [])}
    for src in (EDGE, "tag:edge-standby"):
        for p in PORTS:
            assert (src, f"{HOST}:{p}") in accepts
        for bad in (22, 8006, 7777):                                                # ssh, the hypervisor API, the fleet-msg port stay closed to the edge
            assert (src, f"{HOST}:{bad}") in denies


def test_the_gateway_remap_points_the_domainscope_upstreams_at_the_same_host_and_ports():
    assert EXTRA["extra_vhosts"] == ["domainscope_scrapetheworld_org.conf"]
    targets = {k: v for k, v in EXTRA["remap"].items()}
    assert {int(v.rsplit(":", 1)[1]) for v in targets.values()} == PORTS
    assert {v.rsplit(":", 1)[0] for v in targets.values()} == {HOST}                # the hypervisor's tailnet address, where the DNAT listens
    assert all(k.startswith("10.10.10.30:") for k in targets)                       # VM101's private address, the one thing that is gone with the site
    for k, v in targets.items():                                                    # the same port on both sides: the DNAT does not translate ports
        assert k.rsplit(":", 1)[1] == v.rsplit(":", 1)[1]


def test_the_runner_installer_ships_the_gateway_config():
    s = (REPO / "config/0infer/tier0-runner/install.sh").read_text()
    assert "gateway-extra.json /etc/tier0-runner/gateway-extra.json" in s


def test_the_standby_controller_is_configured_for_the_same_vm_ports_and_gateway():
    ctl = json.loads((REPO / "config/0infer/tier0-runner/host/standby-ctl.json").read_text())
    assert {ctl["ports"]["frontend"], ctl["ports"]["api"]} == PORTS                                   # what the DNAT forwards is what the controller health-checks
    assert ctl["guest_ip"] == VM8101                                                                  # the DNAT target is the VM the controller starts
    assert ctl["env_overrides"]["append_csv"]["TRUSTED_PROXIES"] == [ctl["gateway_ip"]]              # the edge's requests arrive from the hypervisor's vmbr70 address: it must be a trusted proxy
    assert ctl["bridge"] == "vmbr70" and ctl["vmid"] == 8101
    assert ctl["prod_dbname"] != ctl["rehearsal_dbname"]                                              # the daily rehearsal runs the REAL ports and the real compose: it must be on another database
    assert ctl["prod_dbname"].startswith("prod_") and ctl["rehearsal_dbname"].startswith("stage_")
    assert "staging_api" not in ctl["ports"] and "staging_frontend" not in ctl["ports"]               # no separate staging stack any more: the rehearsal IS the activation path
