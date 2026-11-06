"""scripts/netpolicy.py: one source of truth for per-VM network rules (Proxmox firewall, guest nftables, DOCKER-USER).

The invariants that matter: every live rule shape is understood (nothing silently ignored), an imported policy drifts from the very
state it came from by exactly nothing, a hand edit on any layer shows up as drift on that layer, the checker flags the real problems
and none of the known artifacts, and the committed policy of the 0mcp host stays valid, renders back to what it describes and
introduces no new finding.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import netpolicy as np  # noqa: E402

POLICY_FILE = ROOT / "config" / "network-policy" / "0mcp.yaml"

CLUSTER_FW = """[OPTIONS]
enable: 1
policy_in: DROP

[IPSET management]
100.64.0.0/10
10.10.10.0/24

[RULES]
IN ACCEPT -p tcp -dport 8006 -source +management
"""

VM_FW = """[OPTIONS]

enable: 1
policy_in: DROP
policy_out: ACCEPT

[RULES]

IN ACCEPT -source 10.10.10.1/32 -p tcp -dport 22
IN ACCEPT -source 10.10.10.40/32 -p tcp -dport 9100 # Prometheus node exporter scrape
IN ACCEPT -source 100.64.0.0/10 -p icmp
IN ACCEPT -source 10.10.10.1/32 -p udp -dport 41641
IN ACCEPT -p tcp -dport 80
IN ACCEPT -p udp -dport 50000:50010
IN ACCEPT -source 10.10.10.51/32 -p vrrp
IN SSH(ACCEPT) -source +management
IN Ping(ACCEPT) -source 10.10.10.10
IN ACCEPT -source 10.10.10.10,10.10.10.30 -p tcp -dport 18021 # keystore
|IN ACCEPT -source 10.10.10.99/32 -p tcp -dport 4444
"""

NFT = """table inet filter {
\tchain input {
\t\ttype filter hook input priority filter; policy drop;
\t\tct state established,related accept
\t\tiifname "lo" accept
\t\tip saddr 10.10.10.1 tcp dport 22 accept
\t\tip saddr 10.10.10.40 tcp dport { 9100, 9101 } accept
\t\tip saddr 10.10.10.1 udp dport 41641 accept
\t\tip saddr 100.64.0.0/10 icmp type echo-request accept
\t\tip saddr 10.10.10.51 ip protocol vrrp accept
\t\ttcp dport { 80, 443 } accept
\t\tudp dport 41641 counter packets 12 bytes 3400 accept
\t\tip saddr { 100.64.0.9, 100.64.0.21 } tcp dport 60072 accept
\t\tiifname "tailscale0" ip saddr 100.1.2.3 tcp dport 18315 accept
\t}
\tchain forward {
\t\ttype filter hook forward priority filter; policy drop;
\t\tct state established,related accept
\t\tip saddr 10.10.10.10 accept
\t\tip saddr 10.10.10.10 ct original proto-dst { 18021, 18023 } accept
\t}
\tchain output {
\t\ttype filter hook output priority filter; policy accept;
\t}
}
table ip filter {
\tchain INPUT {
\t\ttype filter hook input priority filter; policy accept;
\t\tip saddr 1.2.3.4 tcp dport 1 accept
\t}
\tchain FORWARD {
\t\ttype filter hook forward priority filter; policy accept;
\t\taccept
\t}
}
"""

IPT = """-N DOCKER-USER
-A DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdst 10.10.10.91 --ctorigdstport 18021 --ctdir ORIGINAL -j KEYSTORE-LAN
-A DOCKER-USER -j RETURN
-N KEYSTORE-LAN
-A KEYSTORE-LAN -s 10.10.10.10/32 -j RETURN
-A KEYSTORE-LAN -s 10.10.10.30/32 -j RETURN
-A KEYSTORE-LAN -j DROP
"""

CONF = """#!/usr/sbin/nft -f

flush ruleset


table inet filter {
  chain input {
    ip saddr 10.10.10.40/32 tcp dport { 9100, 9101 } accept
    type filter hook input priority 0;
    policy drop;

    iifname "lo" accept
    ct state established,related accept
    ip saddr 10.10.10.1/32 tcp dport { 22 } accept
    ip saddr 10.10.10.1/32 udp dport { 41641 } accept
    ip saddr 100.64.0.0/10 icmp type echo-request accept
    ip saddr 10.10.10.51/32 ip protocol vrrp accept
    tcp dport { 80, 443 } accept
    udp dport { 41641 } accept
    ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport { 60072 } accept
    iifname "tailscale0" ip saddr 100.1.2.3/32 tcp dport { 18315 } accept
  }
  chain forward {
    type filter hook forward priority 0;
    policy drop;
    ct state established,related accept
    ip saddr 10.10.10.10/32 accept
    ip saddr 10.10.10.10/32 ct original proto-dst { 18021, 18023 } accept
  }
  chain output {
    type filter hook output priority 0;
    policy accept;
  }
}
"""


def snapshot(vm_fw=VM_FW, nft=NFT, ipt=IPT, guest_ok=True, conf=CONF) -> dict:
    return {
        "host": "t", "ssh": "hv-t", "cluster_fw": CLUSTER_FW,
        "vms": {"191": {"name": "runtime-general-lv3", "status": "running", "fw": vm_fw, "ip": "10.10.10.91", "qm_net": [],
                        "guest": {"ok": guest_ok, "nft": nft, "nft_table": np._table_text(nft), "iptables": ipt, "conf": conf}}},
    }


def F(src, proto, port, iif=""):
    return np.Flow(src, proto, port, iif)


# ───────────── parsers ─────────────


def test_pve_every_shape_is_understood_and_nothing_is_dropped_silently():
    r = np.parse_pve(VM_FW, {"management": ["100.64.0.0/10", "10.10.10.0/24"]})
    flows = {f for f, _ in r["flows"]}
    assert F("10.10.10.1", "tcp", "22") in flows and F("10.10.10.40", "tcp", "9100") in flows
    assert F("100.64.0.0/10", "icmp", "*") in flows and F("10.10.10.1", "udp", "41641") in flows
    assert F("any", "tcp", "80") in flows and F("any", "udp", "50000-50010") in flows
    assert F("10.10.10.51", "vrrp", "*") in flows
    assert F("100.64.0.0/10", "tcp", "22") in flows and F("10.10.10.0/24", "tcp", "22") in flows, "SSH macro on an ipset expands to every member"
    assert F("10.10.10.10", "icmp", "*") in flows, "Ping macro"
    assert F("10.10.10.10", "tcp", "18021") in flows and F("10.10.10.30", "tcp", "18021") in flows, "comma separated sources"
    assert F("10.10.10.99", "tcp", "4444") not in flows and r["disabled"] == 1, "a disabled rule (leading |) allows nothing"
    assert dict(r["flows"])[F("10.10.10.40", "tcp", "9100")] == "Prometheus node exporter scrape"
    assert r["unparsed"] == [] and r["options"]["policy_in"] == "DROP"


@pytest.mark.parametrize("line,reason", [
    ("OUT ACCEPT -p tcp -dport 22", "only IN"),
    ("IN DROP -source 10.0.0.1/32", "not modelled"),
    ("IN Mystery(ACCEPT) -source 10.0.0.1/32", "macro Mystery"),
    ("IN ACCEPT -source +nosuchset -p tcp -dport 22", "unknown ipset"),
    ("IN ACCEPT -source 10.0.0.1/32 -frobnicate yes", "unknown token"),
    ("IN ACCEPT -dest 10.0.0.9 -p tcp -dport 22", "not modelled"),
    ("IN ACCEPT -source 10.0.0.1/32 -p tcp -dport 99999x", "port"),
])
def test_pve_what_it_does_not_model_is_reported_not_guessed(line, reason):
    r = np.parse_pve("[RULES]\n" + line + "\n", {})
    assert r["flows"] == [] and len(r["unparsed"]) == 1 and reason in r["unparsed"][0]


def test_nft_reads_only_table_inet_filter_and_every_shape():
    r = np.parse_nft(NFT)
    assert r["present"] and r["unparsed"] == []
    inp, fwd = r["chains"]["input"], r["chains"]["forward"]
    assert (inp["policy"], fwd["policy"], r["chains"]["output"]["policy"]) == ("drop", "drop", "accept")
    flows = set(inp["flows"])
    assert F("10.10.10.1", "tcp", "22") in flows
    assert {F("10.10.10.40", "tcp", "9100"), F("10.10.10.40", "tcp", "9101")} <= flows, "port list"
    assert F("100.64.0.0/10", "icmp", "*") in flows and F("10.10.10.51", "vrrp", "*") in flows
    assert {F("any", "tcp", "80"), F("any", "tcp", "443"), F("any", "udp", "41641")} <= flows, "no source, and a counter stripped"
    assert {F("100.64.0.9", "tcp", "60072"), F("100.64.0.21", "tcp", "60072")} <= flows, "source list"
    assert F("100.1.2.3", "tcp", "18315", "tailscale0") in flows, "interface qualified"
    assert F("10.10.10.10", "any", "*") in fwd["flows"] and F("10.10.10.10", "any", "18021") in fwd["flows"] and F("10.10.10.10", "any", "18023") in fwd["flows"]
    assert F("1.2.3.4", "tcp", "1") not in flows and F("any", "any", "*") not in fwd["flows"], "the iptables-nft table is Docker's, not ours"
    assert inp["baseline"] == ['ct state established,related accept', 'iifname "lo" accept']


def test_nft_a_bare_accept_is_an_open_chain_and_an_unknown_shape_is_reported():
    text = 'table inet filter {\n\tchain forward {\n\t\ttype filter hook forward priority filter; policy drop;\n\t\taccept\n\t\tip saddr 10.0.0.1 meta l4proto gre accept\n\t}\n}\n'
    r = np.parse_nft(text)
    assert F("any", "any", "*") in r["chains"]["forward"]["flows"]
    assert len(r["unparsed"]) == 1 and "gre" in r["unparsed"][0]
    assert np.parse_nft("table ip nat {\n}\n")["present"] is False


def test_docker_user_resolves_the_chain_it_jumps_to():
    r = np.parse_docker_user(IPT)
    assert set(r["flows"]) == {F("10.10.10.10", "tcp", "18021"), F("10.10.10.30", "tcp", "18021")}
    assert "KEYSTORE-LAN: -j DROP" in r["baseline"] and r["unparsed"] == []
    odd = np.parse_docker_user("-A DOCKER-USER -p tcp --dport 80 -j DROP\n")
    assert odd["flows"] == [] and len(odd["unparsed"]) == 1


# ───────────── the canonical file ─────────────


def test_import_then_drift_against_the_same_state_is_exactly_empty():
    snap = snapshot()
    policy = np.build_policy(snap)
    res = np.drift(policy, snap)
    assert res["summary"] == {"vms": 1, "vms_drifted": 0, "flows_missing": 0, "flows_extra": 0, "conf_flows_missing": 0, "conf_flows_extra": 0}, res
    assert res["vms"]["191"]["state"] == "in_sync" and res["vms"]["191"]["unparsed"] == []


def test_the_policy_survives_a_yaml_round_trip_and_keeps_hand_written_metadata(tmp_path):
    snap = snapshot()
    path = tmp_path / "t.yaml"
    np.write_policy(np.build_policy(snap), path)
    policy = np.load_policy(path)
    assert np.drift(policy, snap)["summary"]["vms_drifted"] == 0
    g = next(g for g in policy["vms"]["191"]["groups"] if g["ports"] == ["18021"])
    g.update(owner="keystore", decided="2026-10-18", purpose="the failover chain")
    np.write_policy(policy, path)
    again = np.build_policy(snap, np.load_policy(path))  # re-import keeps purpose and owner
    g2 = next(g for g in again["vms"]["191"]["groups"] if g["ports"] == ["18021"])
    assert (g2["owner"], g2["purpose"]) == ("keystore", "the failover chain")


@pytest.mark.parametrize("edit,layer,kind,needle", [
    (lambda s: s["vms"]["191"].__setitem__("fw", VM_FW + "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080\n"), "pve", "extra", "10.10.10.77 tcp/8080"),
    (lambda s: s["vms"]["191"].__setitem__("fw", VM_FW.replace("IN ACCEPT -source 10.10.10.1/32 -p tcp -dport 22\n", "")), "pve", "missing", "10.10.10.1 tcp/22"),
    (lambda s: s["vms"]["191"]["guest"].__setitem__("nft", NFT.replace("ip saddr 10.10.10.1 tcp dport 22 accept", "ip saddr 10.10.10.1 tcp dport 22 accept\n\t\tip saddr 10.10.10.88 tcp dport 22 accept")), "input", "extra", "10.10.10.88 tcp/22"),
    (lambda s: s["vms"]["191"]["guest"].__setitem__("nft", NFT.replace("\t\tip saddr 10.10.10.10 accept\n", "")), "forward", "missing", "10.10.10.10 any/*"),
    (lambda s: s["vms"]["191"]["guest"].__setitem__("iptables", IPT.replace("-A KEYSTORE-LAN -s 10.10.10.30/32 -j RETURN\n", "")), "docker_user", "missing", "10.10.10.30 tcp/18021"),
])
def test_a_hand_edit_on_any_layer_is_drift_on_that_layer(edit, layer, kind, needle):
    policy = np.build_policy(snapshot())
    live = snapshot()
    edit(live)
    res = np.drift(policy, live)
    assert res["vms"]["191"]["state"] == "drift"
    assert needle in res["vms"]["191"]["layers"][layer][kind]
    assert list(res["vms"]["191"]["layers"]) == [layer], "and only on that layer"


def test_drift_attributes_missing_vms_and_unreadable_guests():
    policy = np.build_policy(snapshot())
    live = snapshot(vm_fw=VM_FW.replace("policy_in: DROP", "policy_in: ACCEPT"))
    assert any("policy_in" in a for a in np.drift(policy, live)["vms"]["191"]["attrs"])
    live = snapshot(nft=NFT.replace("chain forward {\n\t\ttype filter hook forward priority filter; policy drop;", "chain forward {\n\t\ttype filter hook forward priority filter; policy accept;"))
    assert any("forward policy" in a for a in np.drift(policy, live)["vms"]["191"]["attrs"])
    extra = snapshot()
    extra["vms"]["999"] = {"name": "new", "status": "running", "fw": "[OPTIONS]\nenable: 1\n", "ip": "10.10.10.99", "guest": {"ok": False}}
    res = np.drift(policy, extra)
    assert res["vms"]["999"]["state"] == "not_in_policy"
    gone = np.drift(policy, {"host": "t", "cluster_fw": CLUSTER_FW, "vms": {}})
    assert gone["vms"]["191"]["state"] == "not_on_host"
    unreadable = np.drift(policy, snapshot(guest_ok=False))
    assert unreadable["vms"]["191"]["state"] == "in_sync" and any("not readable" in a for a in unreadable["vms"]["191"]["attrs"]), \
        "an unreadable guest is said so and is not reported as drift of rules it could not read"


def test_invalid_policy_files_are_rejected(tmp_path):
    def write(text):
        p = tmp_path / "bad.yaml"
        p.write_text(text)
        return p
    with pytest.raises(np.PolicyError):
        np.load_policy(write("version: 2\nhost: x\nvms: {}\n"))
    with pytest.raises(np.PolicyError):
        np.load_policy(write("version: 1\nhost: x\nvms:\n  1: {groups: [{from: [10.0.0.1], proto: tcp, ports: [22], layers: [firewall]}]}\n"))
    with pytest.raises(np.PolicyError):
        np.load_policy(write("version: 1\nhost: x\nvms:\n  1: {groups: [{from: [not-an-ip], proto: tcp, ports: [22], layers: [pve]}]}\n"))
    with pytest.raises(np.PolicyError):
        np.load_policy(write("version: 1\nhost: x\nvms:\n  1: {groups: [{from: [10.0.0.1], proto: tcp, ports: [http], layers: [pve]}]}\n"))


def test_reimport_of_the_same_state_changes_nothing_and_keeps_the_runner_alias(tmp_path):
    snap = snapshot()
    path = tmp_path / "t.yaml"
    pol = np.build_policy(snap)
    pol["collect"] = {"ssh": "hv-runner-alias"}
    np.write_policy(pol, path)
    before = path.read_text()
    np.write_policy(np.build_policy(snap, np.load_policy(path)), path)
    assert path.read_text() == before
    np.write_policy(np.load_policy(path), path)  # a plain load and save (a hand edit through the tool) must not reorder anything either
    assert path.read_text() == before
    assert np.load_policy(path)["collect"]["ssh"] == "hv-runner-alias", "the alias of the machine that imports must not replace the runner's"


def _with_comments(text: str) -> str:
    """The hand written conf of the real VMs: a `# why` after most rules (104 of them on VM 191), and whole-line comments."""
    out = []
    for line in text.split("\n"):
        if line.rstrip().endswith("accept") and not line.lstrip().startswith(("ct state", "iifname \"lo\"")):
            line += "  # 0docker NGINX gateway -> proxy replica; AUTO-MIGRATED 2026-08-26 from hand-authored .fw"
        out.append(line)
        if line.strip().startswith("chain "):
            out.append("    # a comment line that names a rule: ip saddr 10.66.66.66 tcp dport 1 accept")
    return "\n".join(out)


@pytest.mark.parametrize("text", [NFT, CONF], ids=["nft list layout", "hand written conf layout"])
def test_a_trailing_comment_never_changes_what_a_rule_means(text):
    plain, commented = np.parse_nft(text), np.parse_nft(_with_comments(text))
    assert commented["unparsed"] == [] and plain["unparsed"] == []
    for chain in ("input", "forward"):
        assert commented["chains"][chain]["flows"] == plain["chains"][chain]["flows"], chain
        assert commented["chains"][chain]["baseline"] == plain["chains"][chain]["baseline"], "a commented rule is a rule, not baseline"
    assert F("10.66.66.66", "tcp", "1") not in commented["chains"]["input"]["flows"], "a whole-line comment is not a rule"
    assert "#" not in "".join(commented["unparsed"])


def test_a_conf_with_comments_is_in_sync_with_the_live_table_not_a_reboot_hazard():
    # the bug of 2026-10-19: rules ending in `# why` were filed as baseline, so the conf looked 50 flows short and the
    # apply path added a duplicate of a rule that was already there
    policy = np.build_policy(snapshot())
    res = np.drift(policy, snapshot(conf=_with_comments(CONF)))
    assert res["vms"]["191"]["state"] == "in_sync" and res["summary"]["conf_flows_missing"] == res["summary"]["conf_flows_extra"] == 0


@pytest.mark.parametrize("stmt", [
    "ct state invalid drop",
    "ip saddr 10.0.0.9 drop",
    "tcp dport 25 reject",
    'log prefix "nft-drop: " drop',
    "jump other-chain",
    "counter drop  # a comment does not make it harmless",
])
def test_a_rule_that_is_not_an_accept_is_reported_never_filed_as_harmless(stmt):
    text = f'table inet filter {{\n\tchain input {{\n\t\ttype filter hook input priority filter; policy drop;\n\t\t{stmt}\n\t}}\n}}\n'
    r = np.parse_nft(text)
    assert len(r["unparsed"]) == 1 and r["unparsed"][0].startswith("input: ") and "<-" in r["unparsed"][0]
    assert r["chains"]["input"]["baseline"] == [] and r["chains"]["input"]["flows"] == []


# ───────────── the conf a reboot loads ─────────────


def test_the_conf_in_its_hand_written_layout_parses_to_the_same_flows_as_the_live_table():
    live, conf = np.parse_nft(NFT), np.parse_nft(CONF)
    assert conf["unparsed"] == [] and conf["present"]
    for chain in ("input", "forward"):
        assert set(conf["chains"][chain]["flows"]) == set(live["chains"][chain]["flows"]), chain
        assert conf["chains"][chain]["policy"] == live["chains"][chain]["policy"] == "drop"
    assert np.parse_nft("table ip nat {\n}\n")["present"] is False


@pytest.mark.parametrize("edit,chain,kind,needle,count", [
    # a rule added live and never saved: the reboot would lose it (the real finding on VMs 121, 122, 130, 171, 191)
    (lambda c: c.replace("    ip saddr 10.10.10.1/32 tcp dport { 22 } accept\n", ""), "input", "missing", "10.10.10.1 tcp/22", 1),
    (lambda c: c.replace("    ip saddr 10.10.10.10/32 ct original proto-dst { 18021, 18023 } accept\n", ""), "forward", "missing", "10.10.10.10 any/18021", 2),
    # a rule only the conf has: the reboot would bring back something that was removed live (the stale old-network rules)
    (lambda c: c.replace("    iifname \"lo\" accept\n", "    iifname \"lo\" accept\n    ip saddr 192.0.2.1/32 tcp dport { 22 } accept\n"), "input", "extra", "192.0.2.1 tcp/22", 1),
])
def test_a_conf_that_differs_from_the_policy_is_a_reboot_hazard_reported_per_chain(edit, chain, kind, needle, count):
    policy = np.build_policy(snapshot())
    res = np.drift(policy, snapshot(conf=edit(CONF)))
    assert res["vms"]["191"]["state"] == "drift" and res["vms"]["191"]["layers"] == {}, "the live layers are fine; only the reboot differs"
    assert needle in res["vms"]["191"]["conf"][chain][kind]
    assert res["summary"]["conf_flows_missing" if kind == "missing" else "conf_flows_extra"] == count
    text = np.metrics_text(dict(res, vms={"191": dict(res["vms"]["191"], name="x")}), "t", False)
    assert f'netpolicy_conf_flows{{hypervisor="t",vm="191",chain="{chain}",kind="{kind}"}} {count}' in text
    assert 'netpolicy_vm_in_sync{hypervisor="t",vm="191"} 0' in text


def test_a_conf_without_the_table_or_with_another_policy_is_reported():
    policy = np.build_policy(snapshot())
    res = np.drift(policy, snapshot(conf="#!/usr/sbin/nft -f\n"))
    assert any("no table inet filter" in a for a in res["vms"]["191"]["attrs"])
    res = np.drift(policy, snapshot(conf=CONF.replace("type filter hook input priority 0;\n    policy drop;", "type filter hook input priority 0;\n    policy accept;")))
    assert any("conf input policy" in a and "policy drop" in a for a in res["vms"]["191"]["attrs"])


def test_an_old_snapshot_without_a_conf_is_not_judged_on_it_and_an_unreadable_guest_is_not_compared():
    policy = np.build_policy(snapshot())
    old = snapshot()
    del old["vms"]["191"]["guest"]["conf"]
    assert np.drift(policy, old)["vms"]["191"]["state"] == "in_sync"
    assert np.drift(policy, snapshot(guest_ok=False))["vms"]["191"]["conf"] == {}


# ───────────── editing the files ─────────────


def test_every_flow_shape_renders_to_a_rule_that_parses_back_to_exactly_that_flow():
    for fl in (F("10.10.10.1", "tcp", "22"), F("10.10.10.0/24", "udp", "50000-50010"), F("any", "tcp", "443"), F("100.64.0.0/10", "icmp", "*"),
               F("10.10.10.51", "vrrp", "*"), F("10.10.10.10", "any", "18021"), F("10.10.10.10", "any", "*"), F("100.1.2.3", "tcp", "18315", "tailscale0")):
        assert np._nft_rule(np.render_nft_rule(fl)) == [fl], fl
    with pytest.raises(np.PolicyError):
        np.render_nft_rule(F("10.10.10.1", "tcp", "*"))


def test_ports_of_one_source_share_a_line_and_the_lines_parse_back():
    flows = [F("10.10.10.10", "tcp", p) for p in ("8080", "7880", "9000")] + [F("10.10.10.20", "tcp", "22"), F("10.10.10.10", "udp", "53")]
    lines = np.render_nft_rules(flows)
    assert "ip saddr 10.10.10.10 tcp dport { 7880, 8080, 9000 } accept" in lines and "ip saddr 10.10.10.20 tcp dport 22 accept" in lines
    assert sorted({f for l in lines for f in np._nft_rule(l)}, key=np._flow_sort) == sorted(set(flows), key=np._flow_sort)


@pytest.mark.parametrize("text", [NFT, CONF], ids=["nft list layout", "hand written conf layout"])
def test_edit_nft_adds_and_removes_in_either_layout_and_changes_nothing_else(text):
    before = np.parse_nft(text)
    add = [F("10.10.10.77", "tcp", "8080"), F("10.10.10.77", "tcp", "8081"), F("10.10.10.78", "udp", "53")]
    gone = {F("10.10.10.1", "tcp", "22")}
    new = np.edit_nft(text, removals={"input": gone}, adds={"input": add})
    after = np.parse_nft(new)
    assert set(after["chains"]["input"]["flows"]) == (set(before["chains"]["input"]["flows"]) - gone) | set(add)
    assert after["chains"]["forward"] == before["chains"]["forward"] and after["chains"]["input"]["policy"] == "drop"
    assert after["unparsed"] == [] and after["chains"]["input"]["baseline"] == before["chains"]["input"]["baseline"]
    import difflib
    changed = [l for l in difflib.unified_diff(text.splitlines(), new.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert len(changed) == 3, changed  # one rule line out, two in (the two ports of .77 share one line)
    assert np.edit_nft(new, adds={"input": add}) == new, "adding what is already there changes nothing"
    assert np.edit_nft(text) == text, "no edit, no change"


@pytest.mark.parametrize("layout", [NFT, CONF], ids=["nft list layout", "hand written conf layout"])
def test_edit_nft_knows_a_rule_that_has_a_trailing_comment_so_it_never_adds_a_duplicate(layout):
    text = _with_comments(layout)
    have = F("10.10.10.1", "tcp", "22")
    assert np.edit_nft(text, adds={"input": [have]}) == text, "the rule is already there, with its comment: nothing to add"
    out = np.edit_nft(text, removals={"input": {have}})
    assert have not in np.parse_nft(out)["chains"]["input"]["flows"]
    assert len(out.split("\n")) == len(text.split("\n")) - 1, "one line went, the commented rule, whole"
    assert out.count("AUTO-MIGRATED") == text.count("AUTO-MIGRATED") - 1, "only that one rule's comment went with it"


def test_edit_nft_removes_a_rule_whole_when_all_its_flows_go_and_refuses_unknown_chains():
    out = np.edit_nft(NFT, removals={"input": {F("10.10.10.40", "tcp", "9100"), F("10.10.10.40", "tcp", "9101")}})
    assert F("10.10.10.40", "tcp", "9100") not in np.parse_nft(out)["chains"]["input"]["flows"]
    assert "10.10.10.40" not in out and len(out.split("\n")) == len(NFT.split("\n")) - 1
    with pytest.raises(np.PolicyError, match="no chain"):
        np.edit_nft(NFT, adds={"prerouting": [F("10.0.0.1", "tcp", "1")]})
    with pytest.raises(np.PolicyError, match="no table"):
        np.edit_nft("table ip nat {\n}\n", adds={"input": [F("10.0.0.1", "tcp", "1")]})


def test_edit_nft_keeps_the_layout_of_a_hand_written_conf(tmp_path):
    new = np.edit_nft(CONF, removals={"input": {F("100.1.2.3", "tcp", "18315", "tailscale0")}}, adds={"forward": [F("10.10.10.30", "tcp", "9100")]})
    assert new.startswith("#!/usr/sbin/nft -f\n\nflush ruleset\n") and new.count("flush ruleset") == 1, "the header is untouched: never reloaded, only persisted"
    assert "  chain forward {" in new and "    ip saddr 10.10.10.30 tcp dport 9100 accept" in new
    assert 'iifname "tailscale0"' not in new and new.endswith("}\n")


def test_edit_nft_self_check_refuses_a_result_that_is_not_the_intended_flows(monkeypatch):
    monkeypatch.setattr(np, "render_nft_rules", lambda flows: ["ip saddr 10.9.9.9 tcp dport 1 accept"])
    with pytest.raises(np.PolicyError, match="self-check"):
        np.edit_nft(NFT, adds={"input": [F("10.10.10.77", "tcp", "8080")]})


def test_edit_pve_adds_after_the_last_rule_removes_whole_lines_and_keeps_the_rest():
    ipsets = {"management": ["100.64.0.0/10", "10.10.10.0/24"]}
    before = np.parse_pve(VM_FW, ipsets)
    gone = {F("10.10.10.1", "tcp", "22"), F("10.10.10.1", "udp", "41641")}
    add = [(F("10.10.10.77", "tcp", "8080"), "new service"), (F("10.10.10.88", "udp", "53"), "")]
    new = np.edit_pve(VM_FW, gone, add, ipsets)
    after = np.parse_pve(new, ipsets)
    assert {f for f, _ in after["flows"]} == ({f for f, _ in before["flows"]} - gone) | {f for f, _ in add}
    assert "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080 # new service" in new and "|IN ACCEPT -source 10.10.10.99/32" in new, "the disabled rule stays"
    assert new.index("-dport 8080") > new.index("# keystore") and new.endswith("\n")
    assert np.edit_pve(VM_FW, set(), [], ipsets) == VM_FW and np.edit_pve(new, set(), add, ipsets) == new
    empty = np.edit_pve("[OPTIONS]\n\nenable: 1\n", set(), [(F("10.10.10.1", "tcp", "22"), "ssh")])
    assert "[RULES]" in empty and np.parse_pve(empty)["flows"][0][0] == F("10.10.10.1", "tcp", "22")


# ───────────── a rule that keeps some of its flows is rewritten in place (REPLACE) ─────────────
# The case of 2026-10-25 (fleet-host-sunset reports/pve01-vm140-firewall-fix.md): on monitoring-lv3 (VM 140, 0mcp) the input chain (handle 56) and
# the forward chain (handle 121) allow tcp/60072 from four tailnet addresses in one rule, and only pve01's (100.64.0.9, retired) was to go.
# `apply` refused ("split it first") and the owner had to edit the firewall by hand. Here it is a fixture, not a target.

PVE01 = F("100.64.0.9", "tcp", "60072")
VM140_RULE = "ip saddr { 100.64.0.9, 100.64.0.21, 100.64.0.3, 100.64.0.6 } tcp dport 60072 accept"
VM140_KEPT = "ip saddr { 100.64.0.21, 100.64.0.3, 100.64.0.6 } tcp dport 60072 accept"
VM140_NFT = f"""table inet filter {{
\tchain input {{
\t\ttype filter hook input priority filter; policy drop;
\t\tct state established,related accept
\t\tiifname "lo" accept
\t\tip saddr 10.10.10.1 tcp dport 22 accept
\t\t{VM140_RULE}
\t\tip saddr 100.64.0.21 tcp dport {{ 9090, 9093, 9094 }} accept
\t}}
\tchain forward {{
\t\ttype filter hook forward priority filter; policy drop;
\t\tct state established,related accept
\t\t{VM140_RULE.replace(" accept", " counter packets 12 bytes 720 accept")}
\t\tip saddr 100.64.0.21 udp dport 9094 accept
\t}}
}}
"""
VM140_CONF_RULE = "ip saddr { 100.64.0.9/32, 100.64.0.21/32, 100.64.0.3/32, 100.64.0.6/32 } tcp dport { 60072 } accept"
VM140_CONF = f"""#!/usr/sbin/nft -f

flush ruleset

table inet filter {{
  chain input {{
    type filter hook input priority 0;
    policy drop;
    iifname "lo" accept
    ct state established,related accept
    ip saddr 10.10.10.1/32 tcp dport {{ 22 }} accept
    {VM140_CONF_RULE}  # Scanopy failover
    ip saddr 100.64.0.21/32 tcp dport {{ 9090, 9093, 9094 }} accept
  }}
  chain forward {{
    type filter hook forward priority 0;
    policy drop;
    ct state established,related accept
    {VM140_CONF_RULE}
    ip saddr 100.64.0.21/32 udp dport {{ 9094 }} accept
  }}
}}
"""
# the persisted line as it really was on the host: /32 and another order, with the address to go third of four
VM140_CONF_RULE_HOST = "ip saddr { 100.64.0.6/32, 100.64.0.3/32, 100.64.0.9/32, 100.64.0.21/32 } tcp dport { 60072 } accept"
VM140_CONF_HOST = VM140_CONF.replace(VM140_CONF_RULE, VM140_CONF_RULE_HOST)
VM140_FW = "[OPTIONS]\n\nenable: 1\npolicy_in: DROP\n\n[RULES]\n\nIN ACCEPT -source 10.10.10.1/32 -p tcp -dport 22\n"


def vm140_snapshot(nft=VM140_NFT, conf=VM140_CONF) -> dict:
    return {"host": "0mcp", "ssh": "hv-0mcp", "cluster_fw": CLUSTER_FW,
            "vms": {"140": {"name": "monitoring-lv3", "status": "running", "fw": VM140_FW, "ip": "10.10.10.40", "qm_net": [],
                            "guest": {"ok": True, "nft": nft, "nft_table": np._table_text(nft), "iptables": "", "conf": conf}}}}


def without(policy, vmid, src, port):
    """The policy with `src` taken out of every group of the VM that allows `port` (what a PR that retires a host does)."""
    for g in policy["vms"][vmid]["groups"]:
        if src in g["from"] and port in [str(p) for p in g["ports"]]:
            g["from"].remove(src)
    policy["vms"][vmid]["groups"] = [g for g in policy["vms"][vmid]["groups"] if g["from"]]
    return policy


def changed_lines(old: str, new: str) -> list[tuple[int, str, str]]:
    a, b = old.split("\n"), new.split("\n")
    assert len(a) == len(b), "a rewrite changes lines, it never adds or drops one"
    return [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]


@pytest.mark.parametrize("text,old,kept", [
    (VM140_NFT, VM140_RULE, VM140_KEPT),
    (VM140_CONF, VM140_CONF_RULE, VM140_CONF_RULE.replace("100.64.0.9/32, ", "")),
    (VM140_CONF_HOST, VM140_CONF_RULE_HOST, VM140_CONF_RULE_HOST.replace("100.64.0.9/32, ", "")),
], ids=["live table (nft list layout)", "persisted /etc/nftables.conf", "persisted, the host's own order (the address third of four)"])
def test_a_shared_rule_that_loses_one_source_is_rewritten_in_place_with_the_sources_that_stay(text, old, kept):
    rep: list = []
    out = np.edit_nft(text, removals={"input": {PVE01}, "forward": {PVE01}}, replaced=rep)
    before, after = np.parse_nft(text), np.parse_nft(out)
    for chain in ("input", "forward"):
        assert set(after["chains"][chain]["flows"]) == set(before["chains"][chain]["flows"]) - {PVE01}, chain
        assert {F(s, "tcp", "60072") for s in ("100.64.0.21", "100.64.0.3", "100.64.0.6")} <= set(after["chains"][chain]["flows"])
    old_head = old.split(" accept")[0]
    diff = changed_lines(text, out)
    assert [i for i, _, _ in diff] == [i for i, line in enumerate(text.split("\n")) if old_head in line], "the same lines, in the same position"
    for _, x, y in diff:
        assert y == x.replace(old.split(" tcp dport")[0], kept.split(" tcp dport")[0]), "only the source set changed: indent, counter and comment stay"
    assert "100.64.0.9" not in out
    assert sorted((r["chain"], r["old"], r["new"]) for r in rep) == [
        ("forward", np._nft_line(old), np._nft_line(kept)), ("input", np._nft_line(old), np._nft_line(kept))]
    if text is VM140_CONF:
        assert out.startswith("#!/usr/sbin/nft -f\n\nflush ruleset\n") and "  # Scanopy failover" in out


@pytest.mark.parametrize("text,gone,old,new", [
    (NFT, {F("10.10.10.40", "tcp", "9100")}, "ip saddr 10.10.10.40 tcp dport { 9100, 9101 } accept", "ip saddr 10.10.10.40 tcp dport 9101 accept"),
    (CONF, {F("any", "tcp", "80")}, "tcp dport { 80, 443 } accept", "tcp dport 443 accept"),
    (NFT, {F("10.10.10.10", "any", "18021")}, "ip saddr 10.10.10.10 ct original proto-dst { 18021, 18023 } accept",
     "ip saddr 10.10.10.10 ct original proto-dst 18023 accept"),
    (NFT, {F("100.64.0.9", "tcp", "60072")}, "ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport 60072 accept",
     "ip saddr 100.64.0.21 tcp dport 60072 accept"),
], ids=["a port of a port set", "a port of a sourceless rule", "a port of ct original proto-dst", "a source, one left"])
def test_a_rule_that_loses_some_ports_or_sources_keeps_the_rest_in_the_same_line(text, gone, old, new):
    chain = "forward" if "proto-dst" in old else "input"
    out = np.edit_nft(text, removals={chain: gone})
    assert [(x.strip(), y.strip()) for _, x, y in changed_lines(text, out)] == [(old, new)], "one survivor is written without braces"
    assert set(np.parse_nft(out)["chains"][chain]["flows"]) == set(np.parse_nft(text)["chains"][chain]["flows"]) - gone


def test_a_cut_that_no_single_rule_can_hold_is_refused():
    text = NFT.replace("ip saddr 10.10.10.40 tcp dport { 9100, 9101 } accept", "ip saddr { 10.10.10.40, 10.10.10.41 } tcp dport { 9100, 9101 } accept")
    with pytest.raises(np.PolicyError, match="not one set of sources times one set of ports"):  # .40 keeps 9101, .41 keeps both
        np.edit_nft(text, removals={"input": {F("10.10.10.40", "tcp", "9100")}})
    out = np.edit_nft(text, removals={"input": {F("10.10.10.40", "tcp", "9100"), F("10.10.10.40", "tcp", "9101")}})
    assert "ip saddr 10.10.10.41 tcp dport { 9100, 9101 } accept" in out, "a whole source going is one set times one set again"


def test_a_rewritten_line_must_hold_exactly_the_flows_that_stay(monkeypatch):
    monkeypatch.setattr(np, "_shrink_set", lambda code, head, keep, rule: code)  # a rewrite that silently changes nothing
    with pytest.raises(np.PolicyError, match="could not be rewritten to exactly the flows that stay"):
        np.edit_nft(VM140_NFT, removals={"input": {PVE01}})
    monkeypatch.setattr(np, "_shrink_pve_opt", lambda body, opt, keep: body)
    with pytest.raises(np.PolicyError, match="could not be rewritten to exactly the flows that stay"):
        np.edit_pve(VM_FW, {F("10.10.10.10", "tcp", "18021")}, [], {"management": ["100.64.0.0/10", "10.10.10.0/24"]})


PVE_SHARED = """[OPTIONS]

enable: 1
policy_in: DROP

[RULES]

IN ACCEPT -source 10.10.10.10,10.10.10.30/32 -p tcp -dport 18021 -log nolog # keystore
IN ACCEPT -source 10.10.10.1 -p tcp -dport 80,443,8000:8010
IN SSH(ACCEPT) -source 10.10.10.5,10.10.10.6 # admins
IN DNS(ACCEPT) -source 10.10.10.5
IN SSH(ACCEPT) -source +management,10.10.10.99
|IN ACCEPT -source 10.10.10.99/32 -p tcp -dport 4444
"""
MGMT = {"management": ["100.64.0.0/10", "10.10.10.0/24"]}


@pytest.mark.parametrize("gone,old,new", [
    ({F("10.10.10.10", "tcp", "18021")}, "IN ACCEPT -source 10.10.10.10,10.10.10.30/32 -p tcp -dport 18021 -log nolog # keystore",
     "IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 18021 -log nolog # keystore"),
    ({F("10.10.10.1", "tcp", "443")}, "IN ACCEPT -source 10.10.10.1 -p tcp -dport 80,443,8000:8010", "IN ACCEPT -source 10.10.10.1 -p tcp -dport 80,8000:8010"),
    ({F("10.10.10.1", "tcp", "8000-8010")}, "IN ACCEPT -source 10.10.10.1 -p tcp -dport 80,443,8000:8010", "IN ACCEPT -source 10.10.10.1 -p tcp -dport 80,443"),
    ({F("10.10.10.5", "tcp", "22")}, "IN SSH(ACCEPT) -source 10.10.10.5,10.10.10.6 # admins", "IN SSH(ACCEPT) -source 10.10.10.6 # admins"),
    ({F("10.10.10.99", "tcp", "22")}, "IN SSH(ACCEPT) -source +management,10.10.10.99", "IN SSH(ACCEPT) -source +management"),
], ids=["a source", "a port", "a port range", "a source of a macro rule", "a plain source next to an ipset"])
def test_edit_pve_rewrites_a_shared_rule_in_place(gone, old, new):
    rep: list = []
    out = np.edit_pve(PVE_SHARED, gone, [], MGMT, rep)
    assert [(x, y) for _, x, y in changed_lines(PVE_SHARED, out)] == [(old, new)]
    assert rep == [{"old": old, "new": new}]
    assert {f for f, _ in np.parse_pve(out, MGMT)["flows"]} == {f for f, _ in np.parse_pve(PVE_SHARED, MGMT)["flows"]} - gone
    assert "|IN ACCEPT -source 10.10.10.99/32 -p tcp -dport 4444" in out and np.parse_pve(out, MGMT)["disabled"] == 1


@pytest.mark.parametrize("gone,needle", [
    ({F("10.10.10.5", "udp", "53")}, "uses the macro DNS(ACCEPT) (tcp/53, udp/53): a macro cannot be cut"),
    ({F("10.10.10.0/24", "tcp", "22")}, "takes sources from the ipset management"),
    ({F("10.10.10.10", "tcp", "18021"), F("10.10.10.1", "tcp", "80")}, None),
], ids=["a macro cut to one protocol", "an ipset member", "two rules cut in one edit (allowed)"])
def test_edit_pve_refuses_what_one_rule_cannot_say(gone, needle):
    if needle is None:
        out = np.edit_pve(PVE_SHARED, gone, [], MGMT)
        assert [y for _, _, y in changed_lines(PVE_SHARED, out)] == [
            "IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 18021 -log nolog # keystore", "IN ACCEPT -source 10.10.10.1 -p tcp -dport 443,8000:8010"]
        return
    with pytest.raises(np.PolicyError, match=re.escape(needle)):
        np.edit_pve(PVE_SHARED, gone, [], MGMT)


def test_the_plan_shows_a_replace_for_the_live_table_and_the_conf_and_apply_without_yes_changes_nothing(tmp_path, capsys):
    snap = vm140_snapshot()
    policy = without(np.build_policy(snap), "140", "100.64.0.9", "60072")
    plan = np.plan_apply(policy, snap, "140", allow_remove=True)
    assert plan["refusals"] == [] and plan["changes"] == 4, plan
    for block in (plan["layers"], plan["conf"]):
        assert set(block) == {"input", "forward"} and all(d["remove"] == ["100.64.0.9 tcp/60072"] and d["add"] == [] for d in block.values())
    conf_old = np._nft_line(VM140_CONF_RULE)
    for chain in ("input", "forward"):
        assert plan["layers"][chain]["replace"] == [{"old": VM140_RULE, "new": VM140_KEPT}]
        assert plan["conf"][chain]["replace"] == [{"old": conf_old, "new": conf_old.replace("100.64.0.9/32, ", "")}]
        assert ["100.64.0.9", "tcp", "60072", ""] not in plan["expect_after"][chain]
        assert ["100.64.0.21", "tcp", "60072", ""] in plan["expect_after"][chain]
    table = np._table_text(VM140_NFT)
    rows = [i for i, line in enumerate(table.split("\n")) if "100.64.0.9" in line]
    assert [i for i, *_ in changed_lines(table, plan["texts"]["table"])] == rows and len(rows) == 2, "the two rules, where they were"
    assert len(changed_lines(VM140_CONF, plan["texts"]["conf"])) == 2 and plan["texts"]["conf"].count("flush ruleset") == 1
    assert any("--allow-remove" in r for r in np.plan_apply(policy, snap, "140")["refusals"]), "still a removal: still opt-in"
    path, snap_path = tmp_path / "0mcp.yaml", tmp_path / "snap.json"
    np.write_policy(policy, path)
    snap_path.write_text(json.dumps(snap))
    assert np.main(["apply", "--policy", str(path), "--vm", "140", "--snapshot", str(snap_path), "--allow-remove"]) == 0
    out = capsys.readouterr().out
    assert f"  live input REPLACE {VM140_RULE}\n  live input    with {VM140_KEPT}  (same position)\n" in out
    assert "persisted in /etc/nftables.conf (a reboot loads this) forward REPLACE" in out and "REFUSED" not in out
    assert "plan only: nothing was changed" in out


@pytest.mark.parametrize("rule", [
    "ip saddr @tailnet_peers tcp dport 60072 accept",
    "ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport 60072 jump scanopy",
    "ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport 60072 log prefix \"x\" accept",
    "ip saddr { 100.64.0.9, 100.64.0.21 } meta l4proto { tcp, udp } th dport 60072 accept",
], ids=["named set", "jump", "log", "mix of protocols"])
def test_a_shared_rule_the_tool_does_not_model_is_never_rewritten_the_vm_is_refused(rule):
    # such a rule is not read as flows, so apply refuses the whole VM for it; the modelled shared rule of the forward chain is planned as a
    # REPLACE and is not a reason to refuse any more
    snap = vm140_snapshot(nft=VM140_NFT.replace(VM140_RULE, rule, 1), conf=VM140_CONF.replace(VM140_CONF_RULE, rule, 1))
    plan = np.plan_apply(without(np.build_policy(vm140_snapshot()), "140", "100.64.0.9", "60072"), snap, "140", allow_remove=True)
    assert len(plan["refusals"]) == 1 and "does not model" in plan["refusals"][0] and rule in plan["refusals"][0], plan["refusals"]
    assert plan["layers"]["forward"]["replace"] == [{"old": VM140_RULE, "new": VM140_KEPT}]
    # the input chain holds the rule the tool does not model: nothing there is planned as a rewrite, live or persisted
    assert not plan["layers"]["input"].get("replace") and not (plan["conf"].get("input") or {}).get("replace"), plan


# ───────────── check ─────────────


def vm_policy(groups, **over):
    vm = {"name": "t", "ip": "10.10.10.5", "pve": {"enable": "1", "policy_in": "DROP"}, "guest": {"nft": "managed", "input_policy": "drop", "forward_policy": "drop"}, "groups": groups}
    vm.update(over)
    return {"version": 1, "host": "t", "ipsets": {}, "inner_sources": np.DEFAULT_INNER_SOURCES, "lan_networks": ["10.10.10.0/24"], "vms": {"5": vm}}


def ids(policy):
    return {f["id"] for f in np.check(policy)}


def grp(src, proto, ports, layers, **kw):
    g = {"from": src, "proto": proto, "ports": ports, "layers": layers, "purpose": "test"}
    g.update(kw)
    return g


def test_check_flags_each_real_problem():
    both = ["pve", "input"]
    assert ids(vm_policy([grp(["10.10.10.1"], "tcp", ["22"], both)])) == set()
    assert "5:pve-off" in ids(vm_policy([], pve={"enable": "0", "policy_in": "DROP"}))
    assert "5:pve-policy" in ids(vm_policy([], pve={"enable": "1", "policy_in": "ACCEPT"}))
    assert "5:no-guest-nft" in ids(vm_policy([], guest={"nft": "absent"}))
    assert "5:no-guest-nft" not in ids(vm_policy([], guest={"nft": "absent"}, exception="staging"))
    assert "5:guest-forward-policy" in ids(vm_policy([], guest={"nft": "managed", "forward_policy": "accept", "input_policy": "drop"}))
    assert "5:any-source:tcp/80" in ids(vm_policy([grp(["any"], "tcp", ["80"], both)]))
    assert "5:any-source:tcp/80" not in ids(vm_policy([grp(["any"], "tcp", ["80"], both, public=True)]))
    assert "5:open-chain:forward" in ids(vm_policy([grp(["any", "10.10.10.1"], "any", "*", ["forward"])]))
    assert "5:wide:10.0.0.0/8:tcp/22" in ids(vm_policy([grp(["10.0.0.0/8"], "tcp", ["22"], both)]))
    assert not [i for i in ids(vm_policy([grp(["10.0.0.0/8"], "tcp", ["22"], both, wide_ok="peering")])) if ":wide:" in i]
    assert "5:foreign-source:192.0.2.1" in ids(vm_policy([grp(["192.0.2.1"], "tcp", ["22"], both)]))
    assert any(i.startswith("5:purpose:") for i in ids(vm_policy([grp(["10.10.10.1"], "tcp", ["22"], both, purpose="")])))


def test_check_does_not_flag_the_known_artifacts():
    both = ["pve", "input"]
    # docker bridge and tailnet sources never cross the VM's network card, so a guest-only rule for them is normal and a wide range is fine
    quiet = vm_policy([grp(["172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"], "tcp", ["1025"], ["input", "forward"])])
    assert ids(quiet) == set()
    # a guest rule that is WIDER than the Proxmox rule (any protocol, or every port) is the normal design: Proxmox is the narrow gate
    assert ids(vm_policy([grp(["10.10.10.1"], "tcp", ["22"], ["pve"]), grp(["10.10.10.1"], "any", "*", ["forward"]),
                          grp(["10.10.10.1"], "tcp", ["22"], ["input"])])) == set()
    assert ids(vm_policy([grp(["10.10.10.10"], "tcp", ["18021"], ["pve"]), grp(["10.10.10.10"], "any", ["18021"], ["forward"])])) == set(), \
        "ct original proto-dst has no protocol: covered by the tcp rule at the Proxmox layer"
    assert ids(vm_policy([grp(["10.10.10.10"], "tcp", ["18021"], ["pve", "docker_user"]), grp(["10.10.10.10"], "any", "*", ["forward"])])) == set()


def test_check_finds_a_flow_one_layer_allows_and_the_next_one_drops():
    assert "5:shadowed:input:10.10.10.40 tcp/9100" in ids(vm_policy([grp(["10.10.10.40"], "tcp", ["9100"], ["input"])]))
    assert "5:dead-at-guest:10.10.10.1 icmp/*" in ids(vm_policy([grp(["10.10.10.1"], "icmp", "*", ["pve"])]))
    # a rule that is only partly let through still fires: port ranges and source networks that overlap are not findings
    assert ids(vm_policy([grp(["10.10.10.1"], "udp", ["50000-50010"], ["pve"]), grp(["10.10.10.0/24"], "udp", ["50000-59000"], ["input"])])) == set()
    # no overlap at all: a different port, a different source, or a different protocol never meets the other layer
    assert "5:shadowed:input:10.10.10.9 udp/60000" in ids(vm_policy([grp(["10.10.10.1"], "udp", ["50000-50010"], ["pve"]), grp(["10.10.10.9"], "udp", ["60000"], ["input"])]))
    assert "5:shadowed:input:10.10.10.9 tcp/50005" in ids(vm_policy([grp(["10.10.10.1"], "udp", ["50000-50010"], ["pve"]), grp(["10.10.10.9"], "tcp", ["50005"], ["input"])]))
    assert "5:shadowed:input:10.10.10.9 udp/50005" in ids(vm_policy([grp(["10.10.10.1"], "udp", ["50000-50010"], ["pve"]), grp(["10.10.10.9"], "udp", ["50005"], ["input"])]))


def test_check_baseline_marks_known_findings_and_the_cli_fails_only_on_new_ones(tmp_path, capsys):
    policy = vm_policy([grp(["any"], "tcp", ["80"], ["pve", "input"])])
    findings = np.check(policy, baseline={"5:any-source:tcp/80"})
    assert {f["known"] for f in findings} == {"yes"}
    path = tmp_path / "p.yaml"
    np.write_policy(policy, path)
    assert np.main(["check", "--policy", str(path)]) == 1, "a new high finding fails"
    assert np.main(["check", "--policy", str(path), "--json"]) == 1
    (tmp_path / "p.baseline.json").write_text(json.dumps(["5:any-source:tcp/80"]))
    assert np.main(["check", "--policy", str(path)]) == 0
    assert "NEW" not in capsys.readouterr().out.split("\n", 2)[-1]


# ───────────── why, render, metrics ─────────────


def test_why_gives_a_verdict_per_layer_from_the_policy_and_from_the_live_state():
    snap = snapshot()
    policy = np.build_policy(snap)
    res = np.why(policy, "191", "10.10.10.10", "tcp", 18021, snap)
    assert res["layers"]["pve"]["policy"].startswith("allowed by 10.10.10.10 tcp/18021")
    assert res["layers"]["docker_user"]["live"].startswith("allowed")
    assert res["layers"]["forward"]["live"].startswith("allowed by 10.10.10.10 any/*")
    blocked = np.why(policy, "191", "10.10.10.20", "tcp", 18021, snap)
    assert blocked["layers"]["pve"]["policy"] == "NOT allowed" and blocked["layers"]["docker_user"]["live"] == "NOT allowed"
    assert np.why(policy, "191", "10.10.10.50", "udp", 50003, snap)["layers"]["pve"]["policy"] == "allowed by any udp/50000-50010"
    with pytest.raises(np.PolicyError):
        np.why(policy, "999", "10.0.0.1", "tcp", 22)


def test_why_a_layer_that_filters_nothing_is_not_filtered_and_docker_user_only_limits_its_own_ports():
    # an unfiltered VM (no Proxmox firewall, no guest nftables) whose one decision is a DOCKER-USER limit on one port, as VM101 of 0docker
    policy = {"vms": {"101": {"pve": {}, "guest": {"nft": "absent"}, "groups": [
        {"from": ["10.10.10.10"], "proto": "tcp", "ports": ["23481"], "layers": ["docker_user"], "purpose": "x"}]}}}
    ssh = np.why(policy, "101", "10.10.10.10", "tcp", 22)
    assert ssh["layers"]["pve"]["policy"] == "not filtered (the Proxmox firewall is off for this VM)"
    assert ssh["layers"]["input"]["policy"] == "not filtered (no guest nftables)"
    assert ssh["layers"]["docker_user"]["policy"] == "not filtered (no DOCKER-USER rule for tcp/22)"
    assert ssh["verdict"] == {"policy": "passes every layer"}
    assert np.why(policy, "101", "10.10.10.10", "tcp", 23481)["layers"]["docker_user"]["policy"] == "allowed by 10.10.10.10 tcp/23481"
    other = np.why(policy, "101", "10.10.10.50", "tcp", 23481)
    assert other["layers"]["docker_user"]["policy"] == "NOT allowed" and other["verdict"]["policy"] == "dropped by docker_user"
    # a layer that filters keeps saying NOT allowed (the 0mcp shape)
    snap = snapshot()
    policy = np.build_policy(snap)
    res = np.why(policy, "191", "10.10.10.20", "tcp", 18021, snap)
    assert res["verdict"] == {"policy": "dropped by pve, input, forward, docker_user", "live": "dropped by pve, input, forward, docker_user"}
    assert np.why(policy, "191", "10.10.10.20", "tcp", 22, snap)["layers"]["docker_user"]["live"].startswith("not filtered")


def test_render_pve_parses_back_to_exactly_the_flows_it_was_rendered_from():
    policy = np.build_policy(snapshot())
    vm = policy["vms"]["191"]
    text = np.render_pve(vm)
    back = np.parse_pve(text, policy["ipsets"])
    assert {f for f, _ in back["flows"]} == np.expected(vm)["pve"] and back["unparsed"] == []
    assert back["options"]["policy_in"] == "DROP" and "-source 10.10.10.10/32 -p tcp -dport 18021 # keystore" in text
    assert text == np.render_pve(vm), "deterministic"


def test_metrics_cover_every_vm_layer_and_the_dead_mans_switch():
    snap = snapshot()
    policy = np.build_policy(snap)
    live = snapshot(vm_fw=VM_FW + "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080\n")
    res = np.drift(policy, live)
    res["vms"]["191"]["name"] = "runtime-general-lv3"
    text = np.metrics_text(res, "t", False)
    assert 'netpolicy_flows{hypervisor="t",vm="191",layer="pve",kind="extra"} 1' in text
    assert 'netpolicy_flows{hypervisor="t",vm="191",layer="input",kind="extra"} 0' in text
    assert 'netpolicy_vm_in_sync{hypervisor="t",vm="191"} 0' in text and 'netpolicy_could_not_look{hypervisor="t"} 0' in text
    assert "netpolicy_last_run_timestamp_seconds" in text
    blind = np.metrics_text(None, "t", True)
    assert 'netpolicy_could_not_look{hypervisor="t"} 1' in blind and "netpolicy_flows" not in blind


# ───────────── collecting ─────────────


def test_the_collector_that_runs_on_the_hypervisor_is_valid_python():
    compile(np.COLLECTOR, "collector", "exec")


def test_collect_live_failures_are_could_not_look_never_an_empty_policy_match(monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        return subprocess.CompletedProcess(a, 255, stdout="", stderr="Connection timed out")
    monkeypatch.setattr(np.subprocess, "run", boom)
    with pytest.raises(np.PolicyError, match="could not read"):
        np.collect_live("t", "hv-t")
    path = tmp_path / "p.yaml"
    np.write_policy(np.build_policy(snapshot()), path)
    textdir = tmp_path / "prom"
    assert np.main(["drift", "--policy", str(path), "--live", "--textfile-dir", str(textdir)]) == 3
    prom = textdir / "netpolicy_t.prom"
    assert 'netpolicy_could_not_look{hypervisor="t"} 1' in prom.read_text()
    assert prom.stat().st_mode & 0o777 == 0o644, "the node exporter must be able to read it"

    def ok(*a, **k):
        return subprocess.CompletedProcess(a, 0, stdout=json.dumps(snapshot()), stderr="")
    monkeypatch.setattr(np.subprocess, "run", ok)
    assert np.collect_live("t", "hv-t")["vms"]["191"]["name"] == "runtime-general-lv3"
    assert np.main(["drift", "--policy", str(path), "--live", "--textfile-dir", str(textdir)]) == 0
    assert 'netpolicy_could_not_look{hypervisor="t"} 0' in prom.read_text() and not list(textdir.glob(".*")), "replaced atomically, nothing left behind"


# ───────────── the committed policy of the 0mcp host ─────────────


@pytest.fixture(scope="module")
def committed():
    return np.load_policy(POLICY_FILE)


@pytest.mark.parametrize("path", sorted((ROOT / "config" / "network-policy").glob("*.yaml")), ids=lambda p: p.stem)
def test_committed_policy_is_valid_and_has_no_new_finding(path):
    assert np.main(["check", "--policy", str(path)]) == 0
    baseline = set(json.loads(path.with_suffix(".baseline.json").read_text()))
    live_ids = {f["id"] for f in np.check(np.load_policy(path)) if f["severity"] != "info"}
    assert baseline <= live_ids, f"fixed findings must leave the baseline: {sorted(baseline - live_ids)}"


def test_committed_policy_renders_back_to_what_it_describes_for_every_vm(committed):
    for vmid, vm in committed["vms"].items():
        back = np.parse_pve(np.render_pve(vm), committed["ipsets"])
        assert back["unparsed"] == [], (vmid, back["unparsed"])
        assert {f for f, _ in back["flows"]} == np.expected(vm)["pve"], vmid


def test_committed_policy_decisions_stay_decided(committed):
    keystore = [g for g in committed["vms"]["191"]["groups"] if g.get("ports") == ["18021"]]
    assert len(keystore) == 1 and keystore[0]["from"] == ["10.10.10.10", "10.10.10.30"], "the keystore failover path is exactly two hosts"
    assert set(keystore[0]["layers"]) == {"pve", "docker_user"} and keystore[0]["owner"] == "keystore"
    for vmid, vm in committed["vms"].items():
        for g in vm["groups"]:
            if "any" in g["from"] and g.get("public"):
                assert g["from"] == ["any"], f"VM {vmid}: a public group names no other source"


# ───────────── the committed policy of the 0docker host: VM101 DomainScope ports (go-url-categorizer-api#2510 finding 13) ─────────────

DOCKER_PROD_UNIT = ROOT / "config" / "0docker" / "docker-prod-lan-ports"
DOMAINSCOPE_PORTS = ["23480", "23481", "23482", "23483", "23580", "23581"]
DOMAINSCOPE_FROM = ["10.10.10.1", "10.10.10.10", "10.10.10.20", "10.10.10.30", "172.20.0.0/14"]
HAVE_BASH = subprocess.run(["bash", "-c", "true"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def committed_0docker():
    return np.load_policy(ROOT / "config" / "network-policy" / "0docker.yaml")


def _unit(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    base = {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"}
    return subprocess.run(["bash", str(DOCKER_PROD_UNIT / "domainscope-lan-firewall"), *args], capture_output=True, text=True, env={**base, **env})


def test_0docker_vm101_limits_only_the_domainscope_ports_in_docker_user(committed_0docker):
    vm = committed_0docker["vms"]["101"]
    assert len(vm["groups"]) == 1, "one decision on VM101: the DomainScope ports"
    g = vm["groups"][0]
    assert g["layers"] == ["docker_user"], "Docker-published ports are limited in DOCKER-USER; no layer that would turn the VM to deny-all"
    assert (g["from"], g["proto"], g["ports"]) == (DOMAINSCOPE_FROM, "tcp", DOMAINSCOPE_PORTS)
    assert g["owner"] == "domainscope" and g["unit"] == "config/0docker/docker-prod-lan-ports"
    assert vm["pve"] == {} and vm["guest"] == {"nft": "absent"}, "the VM's other ports stay as they are"
    for vmid in ("100", "104"):
        assert committed_0docker["vms"][vmid]["groups"] == [], f"VM {vmid} is imported as it is, nothing changes for it"


@pytest.mark.skipif(not HAVE_BASH, reason="bash")
def test_0docker_the_unit_on_the_vm_holds_exactly_the_policy_flows(committed_0docker):
    r = _unit(["--print"], {"DOMAINSCOPE_LAN_CONF": str(DOCKER_PROD_UNIT / "domainscope-lan-allow.conf")})
    assert r.returncode == 0, r.stderr
    parsed = np.parse_docker_user(r.stdout)
    assert parsed["unparsed"] == [], parsed["unparsed"]
    assert set(parsed["flows"]) == np.expected(committed_0docker["vms"]["101"])["docker_user"], \
        "domainscope-lan-allow.conf and the VM 101 group of 0docker.yaml must list the same sources and ports"
    assert set(parsed["baseline"]) == {"DOMAINSCOPE-LAN: -j DROP"}, "everything not allowed is dropped"
    v6 = [line for line in r.stdout.splitlines() if line.startswith("-A INPUT ")]
    assert sorted(line.split("--dport ")[1].split()[0] for line in v6) == DOMAINSCOPE_PORTS, "the IPv6 path to docker-proxy is closed for the same ports"
    assert all(" -i eth0 " in line for line in r.stdout.splitlines() if " -j DOMAINSCOPE-LAN" in line), "only what arrives from the LAN"


@pytest.mark.skipif(not HAVE_BASH, reason="bash")
@pytest.mark.parametrize("line", ["allow 0.0.0.0", "allow 10.10.10.0/4", "allow any", "allow 10.10.10.256", "port 70000", "port 80 443",
                                  "deny 10.0.0.1", "allow 10.10.10.10 # ok\nallow 1.2.3.4/33"])
def test_0docker_the_unit_refuses_a_bad_conf_line(tmp_path, line):
    conf = tmp_path / "c.conf"
    conf.write_text("port 23481\n" + line + "\n")
    r = _unit(["--print"], {"DOMAINSCOPE_LAN_CONF": str(conf)})
    assert r.returncode == 2 and "refusing" in r.stderr


FAKE_IPT = r'''
# A fake iptables / *-restore over a JSON state file: enough of -S -C -I -D -F -X and `restore --noflush` for the unit.
import json, os, sys
path = os.environ["FAKE_STATE_" + sys.argv[1]]
st = json.load(open(path))
args = sys.argv[2:]
def save():
    json.dump(st, open(path, "w"))
if args and args[0] == "--noflush":
    for line in sys.stdin.read().splitlines():
        if line.startswith(":"):
            st[line[1:].split()[0]] = []
        elif line.startswith("-A "):
            chain, rule = line[3:].split(" ", 1)
            st.setdefault(chain, []).append(rule)
    save()
    sys.exit(0)
op, chain, rest = args[0], args[1], args[2:]
if op == "-S":
    if chain not in st:
        sys.exit(1)
    print("-N " + chain)
    for r in st[chain]:
        print(f"-A {chain} {r}")
elif op == "-C":
    sys.exit(0 if " ".join(rest) in st.get(chain, []) else 1)
elif op == "-I":
    st.setdefault(chain, []).insert(int(rest[0]) - 1, " ".join(rest[1:]))
    save()
elif op == "-D":
    st[chain].remove(" ".join(rest))
    save()
elif op in ("-F", "-X"):
    if chain not in st:
        sys.exit(1)
    if op == "-F":
        st[chain] = []
    else:
        del st[chain]
    save()
'''


@pytest.mark.skipif(not HAVE_BASH, reason="bash")
def test_0docker_the_unit_is_idempotent_drops_stale_ports_keeps_other_rules_and_removes_cleanly(tmp_path):
    fake = tmp_path / "fake_ipt.py"
    fake.write_text(FAKE_IPT)
    s4, s6 = tmp_path / "v4.json", tmp_path / "v6.json"
    unrelated = "-i eth0 -p tcp -m conntrack --ctorigdstport 18329 --ctdir ORIGINAL -j OTHER"
    stale = "-i eth0 -p tcp -m conntrack --ctorigdstport 9999 --ctdir ORIGINAL -j DOMAINSCOPE-LAN"
    s4.write_text(json.dumps({"DOCKER-USER": [unrelated, stale], "OTHER": ["-j RETURN"]}))
    s6.write_text(json.dumps({"INPUT": ["-j ts-input"]}))
    env = {"DOMAINSCOPE_LAN_CONF": str(DOCKER_PROD_UNIT / "domainscope-lan-allow.conf"), "FAKE_STATE_v4": str(s4), "FAKE_STATE_v6": str(s6)}
    for var, name, which in (("IPTABLES", "iptables", "v4"), ("IPTABLES_RESTORE", "iptables-restore", "v4"),
                             ("IP6TABLES", "ip6tables", "v6"), ("IP6TABLES_RESTORE", "ip6tables-restore", "v6")):
        shim = tmp_path / name
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" {which} "$@"\n')
        shim.chmod(0o755)
        env[var] = str(shim)
    for _ in range(2):
        r = _unit([], env)
        assert r.returncode == 0, r.stderr
    v4, v6 = json.loads(s4.read_text()), json.loads(s6.read_text())
    jumps = [x for x in v4["DOCKER-USER"] if x.endswith("-j DOMAINSCOPE-LAN")]
    assert sorted(x.split("--ctorigdstport ")[1].split()[0] for x in jumps) == DOMAINSCOPE_PORTS, "once per port, and the stale 9999 is gone"
    assert unrelated in v4["DOCKER-USER"] and v4["OTHER"] == ["-j RETURN"], "other rules and chains are untouched"
    assert v4["DOMAINSCOPE-LAN"] == [f"-s {s} -j RETURN" for s in DOMAINSCOPE_FROM] + ["-j DROP"]
    assert v6["INPUT"].count("-j ts-input") == 1 and len([x for x in v6["INPUT"] if x.endswith("-j DOMAINSCOPE-LAN6")]) == len(DOMAINSCOPE_PORTS)
    assert v6["DOMAINSCOPE-LAN6"] == ["-j DROP"]
    r = _unit(["--remove"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(s4.read_text()) == {"DOCKER-USER": [unrelated], "OTHER": ["-j RETURN"]}, "the rollback leaves exactly the rest"
    assert json.loads(s6.read_text()) == {"INPUT": ["-j ts-input"]}


def test_a_reimport_keeps_a_recorded_address_and_unit_when_the_collector_finds_none():
    snap = snapshot()
    previous = np.build_policy(snap)
    previous["vms"]["191"]["groups"][0]["unit"] = "config/some/unit"
    snap["vms"]["191"]["ip"] = ""  # the collector reads eth0 only; VMs on ens18 come back without an address
    again = np.build_policy(snap, previous)
    assert again["vms"]["191"]["ip"] == "10.10.10.91"
    assert again["vms"]["191"]["groups"][0].get("unit") == "config/some/unit"
