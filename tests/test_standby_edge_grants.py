"""scripts/standby_edge_grants.py: the grants and tests that close the gap between what the standby gateway's pools use and what its tailnet access allows (2026-10-18: 103 of 293 backend ports)."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "standby_edge_grants.py"
FIXTURE = ROOT / "tests" / "fixtures" / "standby_edge_reach_2026-10-18.txt"
POLICY = ROOT / "config" / "tailscale" / "policy.hujson"
_spec = importlib.util.spec_from_file_location("standby_edge_grants", SCRIPT)
seg = importlib.util.module_from_spec(_spec)
sys.modules["standby_edge_grants"] = seg
_spec.loader.exec_module(seg)
sys.path.insert(0, str(ROOT / "scripts"))
import tailscale_policy_sync as tps  # noqa: E402

EDGE = "100.84.241.55"
RETIRED = {"100.84.14.14"}  # 0database runtime (pve01 VM102), retired 2026-10-21: its grants and tests left the policy

# Everything pve01 (0database.com) had on the tailnet and on its private LAN. Its four VMs were stopped on 2026-10-21 and the server was cancelled on 2026-10-22 (the sources differ), and #546 took
# its grants out of the policy. A Tailscale address can be handed to a new node, which would inherit any access still written for the old one, so no grant, test, ssh rule, host alias, group or tag
# owner may name one of these. Exact names only: a CIDR or range that merely covers an address, and IPv6 forms, are not caught (the policy holds neither for these nodes today).
# If one of these is handed to a NEW node on purpose: in the PR that grants it, delete its entry here, its pin in the control test below and (for 100.84.14.14) RETIRED above, and say why.
RETIRED_PVE01 = {
    "100.64.0.9": "the pve01 hypervisor (tag:pve01-metrics)",
    "100.64.0.10": "pve01 VM100, pg-primary (not the live 0docker VM100)",
    "100.110.164.38": "pve01 VM101, the builder (device pve01-amd64-builder)",
    "100.84.14.14": "pve01 VM102, the runtime (device 0database-runtime)",
    "10.50.0.1": "pve01 LAN: the hypervisor",
    "10.50.0.10": "pve01 LAN: VM100",
    "10.50.0.12": "pve01 LAN: VM102",
    "10.50.0.13": "pve01 LAN: VM103, the SPIRE relay (not a tailnet node)",
}
RETIRED_PVE01_NAMES = ("pve01-amd64-builder", "0database-runtime", "tag:pve01-metrics")
# The one place a retired name may still stand: the tagOwners key of the hypervisor's tag, which #546 kept until the device is deleted from the tailnet. The PR that removes the key needs no edit here.
RETIRED_PVE01_ALLOWED = {("policy.tagOwners.tag:pve01-metrics (key)", "tag:pve01-metrics")}


def test_consecutive_needed_ports_become_ranges_and_nothing_else_does():
    assert seg.compress([8083, 8084, 8085, 8087, 3002, 8083]) == ["tcp:3002", "tcp:8083-8085", "tcp:8087"]          # 8086 is not needed: no range may span it
    assert seg.compress([18004]) == ["tcp:18004"] and seg.compress([]) == []


def test_only_closed_pairs_become_grants_one_per_destination_host_with_a_test_for_every_port():
    reach = ["OPEN 100.1.1.1 80", "CLOSED 100.1.1.1 8083", "CLOSED 100.1.1.1 8084", "CLOSED 100.2.2.2 18004", "garbage", "CLOSED 100.2.2.2 notaport"]
    closed = seg.closed_by_destination(reach)
    assert closed == {"100.1.1.1": {8083, 8084}, "100.2.2.2": {18004}}
    grants, tests = seg.build(closed, "100.84.241.55/32")
    assert grants == [{"src": ["100.84.241.55/32"], "dst": ["100.1.1.1/32"], "ip": ["tcp:8083-8084"]}, {"src": ["100.84.241.55/32"], "dst": ["100.2.2.2/32"], "ip": ["tcp:18004"]}]
    assert tests == [{"src": EDGE, "accept": ["100.1.1.1:8083", "100.1.1.1:8084"], "proto": "tcp"}, {"src": EDGE, "accept": ["100.2.2.2:18004"], "proto": "tcp"}]
    assert seg.verify(grants, tests) == []                                                                          # the unattended reconciler's own guard accepts what is generated


def test_a_management_port_is_refused_by_the_guard_not_silently_granted(tmp_path):
    reach = tmp_path / "r.txt"
    reach.write_text("CLOSED 100.9.9.9 8006\nCLOSED 100.9.9.9 18004\n")
    r = subprocess.run([sys.executable, str(SCRIPT), "--reach", str(reach), "--verify"], capture_output=True, text=True)
    assert r.returncode == 3 and "management" in r.stderr and r.stdout == ""
    reach.write_text("OPEN 100.9.9.9 18004\n")
    assert subprocess.run([sys.executable, str(SCRIPT), "--reach", str(reach)], capture_output=True, text=True).returncode == 10     # nothing closed: nothing to grant


@pytest.mark.skipif(not POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_the_committed_policy_grants_every_port_the_measurement_found_closed_and_tests_each_one():
    """The first block (generated from the 2026-10-18 measurement) is in the policy, every port proven by a test. The job's later additions are separate blocks above the END markers."""
    closed = seg.closed_by_destination(FIXTURE.read_text().splitlines())
    assert sum(len(v) for v in closed.values()) == 103 and set(closed) == {"100.64.0.24", "100.102.176.103", "100.120.149.126", "100.84.14.14"}
    sync_spec = importlib.util.spec_from_file_location("tailscale_policy_sync", ROOT / "scripts" / "tailscale_policy_sync.py")
    sync = importlib.util.module_from_spec(sync_spec)
    sys.modules["tailscale_policy_sync"] = sync
    sync_spec.loader.exec_module(sync)
    policy = sync.parse_hujson(POLICY.read_text())                                                                  # the policy tool's own HuJSON parser

    def granted(ip):
        ports = set()
        for g in policy["grants"]:
            if g.get("src") == [f"{EDGE}/32"] and g.get("dst") == [f"{ip}/32"]:
                for rule in g["ip"]:
                    lo, _, hi = rule.split(":")[1].partition("-")
                    ports |= set(range(int(lo), int(hi or lo) + 1))
        return ports
    accepted = {a for t in policy["tests"] if t.get("src") == EDGE for a in t.get("accept", [])}
    for ip, ports in closed.items():
        if ip in RETIRED:
            assert not granted(ip) and not [a for a in accepted if a.startswith(ip + ":")], ip                     # a retired host keeps no grant: its address can be reused
            continue
        assert ports <= granted(ip), (ip, sorted(ports - granted(ip)))
        assert {f"{ip}:{p}" for p in ports} <= accepted, ip                                                         # and every one is proven by a policy test
        # At least the measured ports. Since 2026-10-18 the tier0-edge-grants job on CT108 APPENDS grants for ports that stay closed (above the END markers), so the policy may grant more than this
        # snapshot of 2026-10-18; what it may never do is grant outside the pool runtimes' pool ports (scripts/standby_edge_grants_job.py, tests/test_standby_edge_grants_job.py).


@pytest.mark.skipif(not POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_the_committed_policy_still_denies_ssh_and_the_database_to_the_edge():
    text = POLICY.read_text()
    assert '"deny":  ["100.64.0.24:22", "100.64.0.22:5432", "100.102.176.103:22"]' in text                   # the existing negative tests stay: this change only adds backend ports


@pytest.mark.skipif(not POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_the_committed_grants_and_tests_are_byte_for_byte_what_the_generator_prints_in_the_form_tailscale_stores():
    """Tailscale re-formats the policy on save (consecutive single-line values aligned). A git file that is not already in that form is a whitespace-only difference that the unattended
    reconciler would apply again and again (found 2026-10-18 with the three single-line grants of this block): the generator prints the stored form and this pins the policy to it."""
    closed = {ip: ports for ip, ports in seg.closed_by_destination(FIXTURE.read_text().splitlines()).items() if ip not in RETIRED}
    grants, tests = seg.build(closed, "100.84.241.55/32")
    text = POLICY.read_text()
    assert seg.hujson(grants) in text, "the generated grants block is not in the policy as printed"
    assert seg.hujson(tests) in text, "the generated tests block is not in the policy as printed"


def test_single_line_values_are_aligned_and_multi_line_ones_are_not():
    out = seg.hujson([{"src": ["100.1.1.1/32"], "dst": ["100.2.2.2/32"], "ip": ["tcp:1"]}]).splitlines()
    assert out[1:4] == ['\t\t\t"src": ["100.1.1.1/32"],', '\t\t\t"dst": ["100.2.2.2/32"],', '\t\t\t"ip":  ["tcp:1"],']          # "ip" is padded under "src"/"dst"
    long_ports = ["tcp:%d" % p for p in range(1000, 1030, 2)]
    out = seg.hujson([{"src": ["100.1.1.1/32"], "dst": ["100.2.2.2/32"], "ip": long_ports}]).splitlines()
    assert out[3] == '\t\t\t"ip": [' and out[-2] == '\t\t\t],' and out[-1] == '\t\t},'                                                               # a multi-line list stays unpadded


def test_a_four_endpoint_test_is_printed_expanded_the_way_tailscale_stores_it():
    """2026-10-21: the four `100.84.14.14:80xx` endpoints of #533 (68 characters of endpoints, an 84-character one-line list) were printed on one line, Tailscale stored them expanded, and the
    whitespace-only difference kept FleetTailnetPolicyOutOfSync firing and the reconciler re-applying the text. The two-endpoint test of the same change stays on one line (live: stored as written)."""
    four = {"src": "100.84.241.55", "accept": ["100.84.14.14:%d" % p for p in (8096, 8281, 8290, 8298)], "proto": "tcp"}
    two = {"src": "100.84.241.55", "accept": ["100.64.0.24:8281", "100.64.0.24:8284"], "proto": "tcp"}
    out = seg.hujson([four]).splitlines()
    assert out[1:] == ['\t\t\t"src": "100.84.241.55",', '\t\t\t"accept": [', *['\t\t\t\t"100.84.14.14:%d",' % p for p in (8096, 8281, 8290, 8298)], '\t\t\t],', '\t\t\t"proto": "tcp",', '\t\t},']
    assert seg.hujson([two]).splitlines()[2] == '\t\t\t"accept": ["100.64.0.24:8281", "100.64.0.24:8284"],'
    # the longest single-line list the live policy holds (78 characters of JSON) stays on one line, the old sum-of-lengths rule still applies
    assert seg.hujson([{"dst": ["100.1.1.1:1111", "100.1.1.1:2222", "100.1.1.1:3333"]}]).count("\n") == 2
    assert '"ip": [' in seg.hujson([{"ip": ["tcp:%d" % p for p in range(1000, 1030, 2)]}])


@pytest.mark.skipif(not POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_the_four_endpoint_test_of_533_left_with_its_retired_host():
    """#533's four-endpoint test targeted the 0database runtime; it went with pve01 on 2026-10-21 (the stored form is still pinned by the test above)."""
    text = POLICY.read_text()
    four = {"src": "100.84.241.55", "accept": ["100.84.14.14:%d" % p for p in (8096, 8281, 8290, 8298)], "proto": "tcp"}
    assert seg.hujson([four]) not in text and not [ip for ip in RETIRED if '"%s' % ip in text]


def _policy_strings(value, path="policy"):
    """Every string in a parsed policy and where it sits. Dict keys count too (a `hosts` alias, a `tagOwners` key); comments are already gone after parsing."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _policy_strings(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.{key} (key)", key
            yield from _policy_strings(item, f"{path}.{key}")


def retired_pve01_named(policy):
    """[(where, text, identity)] for every string that names a retired pve01 address (not directly after a digit or a dot, and not before a digit) or device name or tag, except RETIRED_PVE01_ALLOWED."""
    found = []
    for where, text in _policy_strings(policy):
        for ip in RETIRED_PVE01:
            if re.search(r"(?<![\d.])%s(?!\d)" % re.escape(ip), text):
                found.append((where, text, ip))
        for name in RETIRED_PVE01_NAMES:
            if name in text.lower() and (where, name) not in RETIRED_PVE01_ALLOWED:
                found.append((where, text, name))
    return found


@pytest.mark.skipif(not POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_no_retired_pve01_address_or_device_name_is_named_anywhere_in_the_committed_policy():
    """pve01 left the tailnet. Its addresses, device names and tag must not return to any grant, test, ssh rule, host alias, group or tag owner (the one tagOwners key is allowed)."""
    policy = tps.parse_hujson(POLICY.read_text())
    assert len(list(_policy_strings(policy))) > 200, "the walk saw almost nothing: the check would pass on any policy"
    assert RETIRED <= set(RETIRED_PVE01), "RETIRED (above) lists an address that RETIRED_PVE01 does not: keep the two in step"
    named = retired_pve01_named(policy)
    assert not named, ("a retired pve01 identity is back in the policy: "
                       + "; ".join(f"{w}: {t!r} ({RETIRED_PVE01.get(i, 'retired device name or tag')})" for w, t, i in named)
                       + ". If a NEW node was handed it on purpose, the comment above RETIRED_PVE01 says what to remove.")


def test_the_retired_pve01_check_sees_each_identity_wherever_a_policy_can_name_it_and_ignores_look_alikes():
    def places(s):  # one tiny policy for every place that can hold an address or a device name
        return [
            {"grants": [{"src": [s], "dst": ["tag:x"], "ip": ["tcp:22"]}]},
            {"grants": [{"src": ["tag:x"], "dst": [s + "/32"], "ip": ["tcp:22"]}]},
            {"tests": [{"src": "tag:x", "accept": [s + ":8080"]}]},
            {"tests": [{"src": s, "deny": ["tag:x:22"]}]},
            {"ssh": [{"action": "accept", "src": [s], "dst": ["tag:x"], "users": ["root"]}]},
            {"hosts": {"alias": s}},
            {"hosts": {s: "100.1.1.1"}},
            {"groups": {"group:g": [s]}},
            {"tagOwners": {"tag:x": [s]}},
            {"acls": [{"action": "accept", "src": [s], "dst": ["tag:x:22"]}]},
            {"autoApprovers": {"routes": {"10.0.0.0/24": [s]}}},
            {"nodeAttrs": [{"target": [s], "attr": ["funnel"]}]},
            {"grants": [{"src": ["tag:x"], "dst": ["ip:" + s], "ip": ["tcp:22"]}]},                      # a prefix in front of the identity
            {"ssh": [{"action": "accept", "src": ["tag:x"], "dst": ["tag:x"], "users": ["admin@" + s]}]},  # and a user@ in front of it
        ]
    # removing an identity from the table takes a second, visible edit (this pin); adding one is free
    pinned_ips = {"100.64.0.9", "100.64.0.10", "100.110.164.38", "100.84.14.14", "10.50.0.1", "10.50.0.10", "10.50.0.12", "10.50.0.13"}
    assert pinned_ips <= set(RETIRED_PVE01), "an address left RETIRED_PVE01: if a NEW node was handed it on purpose, remove it from this pin too and say why in the PR"
    assert {"pve01-amd64-builder", "0database-runtime", "tag:pve01-metrics"} <= set(RETIRED_PVE01_NAMES), "a name left RETIRED_PVE01_NAMES: if that is on purpose, remove it from this pin too and say why in the PR"
    for identity in (*RETIRED_PVE01, *RETIRED_PVE01_NAMES):
        for policy in places(identity):
            assert retired_pve01_named(policy), (identity, policy)
    assert retired_pve01_named({"hosts": {"a": "PVE01-AMD64-BUILDER"}}), "device names match in any case"
    for fine in ("100.84.14.140", "1100.84.14.14", "9.100.84.14.14", "100.84.14.15", "100-84-14-14", "100x84x14x14", "10.50.0.11", "10.50.0.100", "0database.com", "pve01-0infer"):
        assert not retired_pve01_named({"hosts": {"a": fine}, "tests": [{"src": fine, "accept": [fine]}]}), fine
    assert retired_pve01_named({"grants": [{"src": ["tag:x"], "dst": ["100.84.14.14:80"]}]}) == [("policy.grants[0].dst[0]", "100.84.14.14:80", "100.84.14.14")]
    # the hypervisor's tag may stand in exactly one place, its tagOwners key; every other use of it is caught
    assert not retired_pve01_named({"tagOwners": {"tag:pve01-metrics": ["group:admins"]}})
    assert retired_pve01_named({"tagOwners": {"tag:pve01-metrics": ["group:admins"], "tag:y": ["tag:pve01-metrics"]}})
    assert retired_pve01_named({"grants": [{"src": ["tag:x"], "dst": ["tag:pve01-metrics"], "ip": ["tcp:8007"]}]})
    assert retired_pve01_named({"tests": [{"src": "tag:pve01-metrics", "accept": ["tag:x:80"]}]})
    # comments are dropped by the parser, so a note that names a retired address is allowed (the guard checks what the policy says, not what it remembers)
    assert not retired_pve01_named(tps.parse_hujson('{"hosts": {"a": "1.1.1.1"} /* 100.84.14.14 retired */}\n// 0database-runtime left the tailnet\n'))
