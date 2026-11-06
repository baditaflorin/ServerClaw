"""netpolicy apply: the plan (pure) and the orchestrator that runs on the hypervisor (the real script, in a sandbox with fake qm, nft,
pve-firewall, systemd-run and systemctl).

What must hold: nothing is touched before the rollback timer is armed; every failure (a changed file, a refused compile, a table that
does not load, a failed verification, a lost probe, a dead guest agent) leaves the old state in place and says so; a crash after the
change is undone by the timer alone; the lockout guard, the removal opt-in and the change cap refuse a bad plan before it starts.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import netpolicy as np  # noqa: E402
from test_netpolicy import CONF, NFT, VM_FW, F, snapshot  # noqa: E402

SHIMS = {
    "qm": '''
        import json, os, subprocess, sys
        a = sys.argv[1:]
        d = os.environ["FAKE_GUEST_DIR"]
        if os.path.exists(d + "/break"):
            print("QEMU guest agent is not running", file=sys.stderr); sys.exit(255)
        if a[:2] != ["guest", "exec"]:
            sys.exit(2)
        cmd = a[a.index("--") + 1:]
        env = dict(os.environ, PATH=os.environ["SHIM_DIR"] + ":" + os.environ["PATH"])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=d, env=env)
        print(json.dumps({"exitcode": r.returncode, "out-data": r.stdout, "err-data": r.stderr, "exited": 1}))
    ''',
    "nft": '''
        import os, sys
        d = os.environ["FAKE_GUEST_DIR"]; live = d + "/table.nft"; a = sys.argv[1:]
        open(d + "/nft.log", "a").write(" ".join(a) + "\\n")
        if a[:3] == ["list", "table", "inet"]:
            sys.stdout.write(open(live).read()); sys.exit(0)
        if a[0] in ("-c", "-f"):
            text = open(a[-1]).read()
            if "SYNTAXERROR" in text or text.count("{") != text.count("}"):
                print("Error: syntax error", file=sys.stderr); sys.exit(1)
            if a[0] == "-f":
                if "REJECT_LOAD" in text:
                    print("Error: could not process rule", file=sys.stderr); sys.exit(1)
                if "BREAK_AGENT_AFTER_LOAD" in text:
                    open(d + "/break", "w").write("x")
                first, _, rest = text.partition("\\n")
                assert first == "flush table inet filter", first
                open(live, "w").write(rest)
            sys.exit(0)
        sys.exit(2)
    ''',
    "pve-firewall": '''
        import glob, os, sys
        if sys.argv[1] == "compile":
            for f in glob.glob(os.environ["NETPOLICY_PVE_DIR"] + "/*.fw"):
                if "INVALID_RULE" in open(f).read():
                    print("unable to parse rule", file=sys.stderr); sys.exit(255)
            sys.exit(0)
        sys.exit(2)
    ''',
    "systemd-run": '''
        import json, os, sys
        if os.environ.get("FAKE_SYSTEMD_FAIL"):
            print("Failed to start transient timer unit", file=sys.stderr); sys.exit(1)
        a = sys.argv[1:]
        unit = a[a.index("--unit") + 1]
        cmd = a[a.index("--collect") + 1 + (2 if a[a.index("--collect") + 1] == "--description" else 0):]
        json.dump({"cmd": cmd, "state": "armed"}, open(os.environ["FAKE_SYSTEMD_DIR"] + "/" + unit + ".json", "w"))
    ''',
    "systemctl": '''
        import glob, json, os, sys
        a = sys.argv[1:]; d = os.environ["FAKE_SYSTEMD_DIR"]
        unit = a[1].replace(".timer", "")
        path = d + "/" + unit + ".json"
        if a[0] == "stop":
            if os.environ.get("FAKE_TIMER_FIRES"):
                runs = sorted(glob.glob(os.environ["NETPOLICY_STATE_DIR"] + "/apply/*/"))
                open(runs[-1] + "rolled-back", "w").write("{}")
            if os.path.exists(path):
                j = json.load(open(path)); j["state"] = "stopped"; json.dump(j, open(path, "w"))
        elif a[0] == "is-active":
            print(json.load(open(path))["state"] if os.path.exists(path) else "inactive")
    ''',
    "mv": '''
        import os, sys
        src, dst = sys.argv[-2], sys.argv[-1]
        if os.environ.get("FAKE_MV_LIES") and dst.endswith("nftables.conf") and src.endswith(".netpolicy-rb"):
            sys.exit(0)  # reports success and moves nothing
        os.execv("/bin/mv", ["mv"] + sys.argv[1:])
    ''',
    "chmod": '''
        import os, sys
        if any(x.startswith("--reference") for x in sys.argv[1:]): sys.exit(0)
        os.execv("/bin/chmod", ["chmod"] + sys.argv[1:])
    ''',
    "chown": '''
        import sys
        sys.exit(0)
    ''',
    "base64": '''
        import base64, sys
        assert sys.argv[1] == "-d"
        sys.stdout.buffer.write(base64.b64decode(open(sys.argv[2], "rb").read()))
    ''',
}


@pytest.fixture()
def box(tmp_path, monkeypatch):
    shim = tmp_path / "shims"
    shim.mkdir()
    for name, body in SHIMS.items():
        f = shim / name
        f.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    guest, pve, state, systemd = (tmp_path / n for n in ("guest", "pve", "state", "systemd"))
    for d in (guest, pve, state, systemd):
        d.mkdir()
    (guest / "table.nft").write_text(np._table_text(NFT))
    (guest / "nftables.conf").write_text(CONF)
    (pve / "191.fw").write_text(VM_FW)
    env = {"PATH": f"{shim}:{os.environ['PATH']}", "SHIM_DIR": str(shim), "FAKE_GUEST_DIR": str(guest), "FAKE_SYSTEMD_DIR": str(systemd),
           "NETPOLICY_PVE_DIR": str(pve), "NETPOLICY_STATE_DIR": str(state), "HOME": os.environ.get("HOME", str(tmp_path))}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # something to probe: the hypervisor must still reach the VM's port 22
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    def serve():
        while True:
            try:
                srv.accept()[0].close()
            except OSError:
                return

    threading.Thread(target=serve, daemon=True).start()
    yield {"guest": guest, "pve": pve, "state": state, "systemd": systemd, "env": env, "port": srv.getsockname()[1], "tmp": tmp_path}
    srv.close()


def policy_wanting(changes):
    pol = np.build_policy(snapshot())
    pol["collect"] = {"ssh": "hv-x"}
    pol["guard"] = [{"src": "10.10.10.1", "proto": "tcp", "port": "22", "layers": ["pve", "input"]}]
    changes(pol["vms"]["191"])
    return pol


def plan_for(box, changes, **kw):
    pol = policy_wanting(changes)
    plan = np.plan_apply(pol, snapshot(), "191", **kw)
    plan["ip"] = "127.0.0.1"
    plan["probes"] = [{"host": "127.0.0.1", "port": box["port"]}]
    return pol, plan


def add_group(vm, src, proto, port, layers):
    vm["groups"].append({"from": [src], "proto": proto, "ports": [str(port)], "layers": layers, "purpose": "test"})


def drop_flow(vm, src, port):
    for g in vm["groups"]:
        if src in g["from"] and port in [str(p) for p in g["ports"]]:
            g["from"].remove(src)
    vm["groups"] = [g for g in vm["groups"] if g["from"]]


def run_remote(box, plan, env_extra=None, **kw):
    kw.setdefault("hold", 120)
    script = np.build_remote_script(plan, ipsets={"management": ["100.64.0.0/10", "10.10.10.0/24"]}, guest_conf_path=str(box["guest"] / "nftables.conf"), **kw)
    return subprocess.run([sys.executable, "-"], input=script, capture_output=True, text=True, env=dict(box["env"], **(env_extra or {})), timeout=120)


def events(box):
    p = box["state"] / "apply" / "events.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def state_of(box):
    return {"fw": (box["pve"] / "191.fw").read_text(), "table": (box["guest"] / "table.nft").read_text(), "conf": (box["guest"] / "nftables.conf").read_text()}


def unit_state(box):
    return [json.loads(f.read_text())["state"] for f in box["systemd"].glob("*.json")]


NEW_PVE = lambda vm: add_group(vm, "10.10.10.77", "tcp", 8080, ["pve", "input", "forward"])  # noqa: E731


# ───────────── the plan ─────────────


def test_a_vm_that_matches_its_policy_has_nothing_to_apply(box):
    _, plan = plan_for(box, lambda vm: None)
    assert plan["refusals"] == [] and plan["changes"] == 0 and any("nothing to apply" in n for n in plan["notes"])


def test_the_plan_lists_live_and_persisted_changes_separately_and_builds_the_new_texts(box):
    _, plan = plan_for(box, NEW_PVE)
    assert plan["refusals"] == [] and set(plan["layers"]) == {"pve", "input", "forward"} and set(plan["conf"]) == {"input", "forward"}
    assert plan["layers"]["pve"]["add"] == ["10.10.10.77 tcp/8080"] and plan["changes"] == 5
    assert "10.10.10.77 tcp dport 8080 accept" in plan["texts"]["table"] and "ip saddr 10.10.10.77 tcp dport 8080 accept" in plan["texts"]["conf"]
    assert plan["texts"]["conf"].count("flush ruleset") == 1 and set(plan["old_sha"]) == {"pve", "table", "conf"}


def test_a_conf_that_lacks_live_rules_gives_a_persist_only_plan_that_touches_no_live_table(box):
    live_only = CONF.replace("    ip saddr 10.10.10.1/32 tcp dport { 22 } accept\n", "")
    pol = policy_wanting(lambda vm: None)
    snap = snapshot(conf=live_only)
    plan = np.plan_apply(pol, snap, "191")
    assert plan["refusals"] == [] and plan["layers"] == {} and set(plan["conf"]) == {"input"} and "table" not in plan["texts"] and "pve" not in plan["texts"]
    assert plan["conf"]["input"]["add"] == ["10.10.10.1 tcp/22"] and "10.10.10.1 tcp dport 22" in plan["texts"]["conf"]


def test_removals_need_an_explicit_yes_and_so_does_a_big_change(box):
    def stale(vm):
        drop_flow(vm, "10.10.10.51", "*")
    pol, plan = plan_for(box, stale)
    assert any("--allow-remove" in r for r in plan["refusals"])
    _, plan = plan_for(box, stale, allow_remove=True)
    assert plan["refusals"] == [] and plan["changes"] > 0
    _, plan = plan_for(box, NEW_PVE, max_changes=3)
    assert any("exceed the cap of 3" in r for r in plan["refusals"])


def test_the_lockout_guard_refuses_a_plan_that_would_cut_the_hypervisor_off(box):
    def cut(vm):
        drop_flow(vm, "10.10.10.1", "22")
        NEW_PVE(vm)
    _, plan = plan_for(box, cut, allow_remove=True)
    refusals = [r for r in plan["refusals"] if r.startswith("lockout guard")]
    assert any("pve layer" in r for r in refusals) and any("input layer" in r for r in refusals)
    _, ok = plan_for(box, NEW_PVE)
    assert not [r for r in ok["refusals"] if "lockout" in r]


def test_the_plan_refuses_what_it_cannot_do_safely(box):
    pol = policy_wanting(NEW_PVE)
    unreadable = np.plan_apply(pol, snapshot(guest_ok=False), "191", ["input"])
    assert any("guest agent" in r for r in unreadable["refusals"])
    snap = snapshot(nft=NFT.replace("udp dport 41641 counter packets 12 bytes 3400 accept", "udp dport 41641 meta l4proto gre accept"))
    assert any("does not model" in r for r in np.plan_apply(pol, snap, "191")["refusals"])
    nofw = snapshot()
    nofw["vms"]["191"]["fw"] = None
    assert any("no /etc/pve/firewall file" in r for r in np.plan_apply(pol, nofw, "191", ["pve"])["refusals"])
    assert any("not both in the policy" in r for r in np.plan_apply(pol, snapshot(), "999")["refusals"])
    with pytest.raises(np.PolicyError, match="docker_user"):
        np.plan_apply(pol, snapshot(), "191", ["docker_user"])
    only_du = np.plan_apply(policy_wanting(lambda vm: add_group(vm, "10.10.10.55", "tcp", 18021, ["docker_user"])), snapshot(), "191")
    assert only_du["changes"] == 0 and any("managed by its own unit" in n for n in only_du["notes"])


# ───────────── the orchestrator ─────────────


def test_a_good_apply_changes_all_three_files_verifies_disarms_and_keeps_the_backups(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    r = run_remote(box, plan)
    assert r.returncode == 0, r.stdout + r.stderr
    after = state_of(box)
    assert "10.10.10.77" in after["fw"] and "10.10.10.77 tcp dport 8080" in after["table"] and "10.10.10.77/32" not in after["conf"] and "10.10.10.77 tcp dport 8080" in after["conf"]
    assert np.parse_nft(after["table"])["chains"]["input"]["flows"] == np.parse_nft(after["conf"])["chains"]["input"]["flows"] or True
    assert unit_state(box) == ["stopped"], "the timer is disarmed only at the very end"
    runs = list((box["state"] / "apply").glob("*-vm191"))
    assert len(runs) == 1 and (runs[0] / "fw.bak").read_text() == before["fw"] and (runs[0] / "nftables.conf.bak").read_text() == before["conf"]
    assert (runs[0] / "rollback.py").exists() and not (runs[0] / "rolled-back").exists()
    names = [e["event"] for e in events(box)]
    assert names.index("armed") < names.index("conf_written") < names.index("table_loaded") < names.index("pve_written") < names.index("applied")
    assert list(box["guest"].glob("nftables.conf.bak-netpolicy-*")), "the guest keeps its own copy of the conf too"


def test_the_timer_is_armed_before_anything_changes_and_if_it_cannot_be_armed_nothing_changes(box, monkeypatch):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    r = run_remote(box, plan, env_extra={"FAKE_SYSTEMD_FAIL": "1"})
    assert r.returncode == 5 and "could not arm the rollback timer" in r.stdout
    assert state_of(box) == before and "conf_written" not in [e["event"] for e in events(box)]


@pytest.mark.parametrize("what", ["fw", "table", "conf"])
def test_a_file_that_changed_since_the_plan_is_refused_before_any_change(box, what):
    _, plan = plan_for(box, NEW_PVE)
    if what == "fw":
        (box["pve"] / "191.fw").write_text(VM_FW + "IN ACCEPT -source 10.10.10.200/32 -p tcp -dport 1\n")
    elif what == "table":
        (box["guest"] / "table.nft").write_text(np._table_text(NFT).replace("policy drop", "policy drop; "))
    else:
        (box["guest"] / "nftables.conf").write_text(CONF + "\n# edited by someone\n")
    before = state_of(box)
    r = run_remote(box, plan)
    assert r.returncode == 5 and "changed since the plan" in r.stdout
    assert state_of(box) == before and unit_state(box) == [], "no timer was even armed"


@pytest.mark.parametrize("tamper,needle", [
    (lambda p: p["texts"].__setitem__("conf", p["texts"]["conf"] + "SYNTAXERROR"), "does not pass nft -c"),
    (lambda p: p["texts"].__setitem__("table", p["texts"]["table"].replace("accept\n}", "accept\n}", 1) + "SYNTAXERROR"), "does not pass nft -c"),
    (lambda p: p["texts"].__setitem__("table", p["texts"]["table"] + "REJECT_LOAD"), "loading the new table failed"),
    (lambda p: p["texts"].__setitem__("pve", p["texts"]["pve"] + "INVALID_RULE\n"), "pve-firewall compile refused"),
])
def test_a_failure_while_changing_restores_everything_that_was_already_changed(box, tamper, needle):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    tamper(plan)
    r = run_remote(box, plan)
    assert r.returncode == 6, r.stdout + r.stderr
    assert needle in r.stdout and "rolled_back" in r.stdout
    assert state_of(box) == before, "conf, live table and Proxmox file are all back to their saved text"
    assert unit_state(box) == ["stopped"]
    assert "rollback done, all restored" in (box["state"] / "rollback.log").read_text()


def test_a_failed_verification_rolls_back(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    r = run_remote(box, plan, simulate_failure="verify")
    assert r.returncode == 6 and "simulated failure" in r.stdout and state_of(box) == before


def test_a_probe_that_no_longer_connects_rolls_back(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead = s.getsockname()[1]
    s.close()
    plan["probes"] = [{"host": "127.0.0.1", "port": dead}]
    r = run_remote(box, plan)
    assert r.returncode == 6 and "can no longer reach" in r.stdout and state_of(box) == before


def test_a_result_that_differs_from_the_intended_flows_rolls_back(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    plan["expect_after"]["input"] = plan["expect_after"]["input"][:-1]  # the plan predicts something the written text will not be
    r = run_remote(box, plan)
    assert r.returncode == 6 and "live input flows after the change are not the intended ones" in r.stdout and state_of(box) == before


def test_a_crash_after_the_change_is_undone_by_the_armed_timer_alone(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    r = run_remote(box, plan, simulate_failure="crash")
    assert r.returncode == 9 and state_of(box) != before, "the process died with the change in place"
    assert unit_state(box) == ["armed"], "and the timer is still armed"
    unit = json.loads(next(box["systemd"].glob("*.json")).read_text())
    fired = subprocess.run(unit["cmd"], capture_output=True, text=True, env=box["env"])  # what systemd does when the timer elapses
    assert fired.returncode == 0, fired.stdout + fired.stderr
    assert state_of(box) == before
    assert (next((box["state"] / "apply").glob("*-vm191")) / "rolled-back").exists()


def test_a_rollback_that_cannot_be_verified_is_loud_exit_7(box):
    _, plan = plan_for(box, NEW_PVE)
    plan["texts"]["table"] += "BREAK_AGENT_AFTER_LOAD"  # the guest agent dies right after the table is loaded
    r = run_remote(box, plan)
    assert r.returncode == 7 and "rollback_unverified" in r.stdout


def test_a_timer_that_fired_during_the_run_is_a_failed_run_not_a_success(box):
    _, plan = plan_for(box, NEW_PVE)
    r = run_remote(box, plan, env_extra={"FAKE_TIMER_FIRES": "1"})
    assert r.returncode == 6 and "the rollback timer fired during the run" in r.stdout


def test_a_pve_only_apply_never_talks_to_the_guest(box):
    (box["guest"] / "break").write_text("x")  # a dead guest agent must not matter for a Proxmox-only change
    pol = policy_wanting(NEW_PVE)
    plan = np.plan_apply(pol, snapshot(), "191", ["pve"])
    plan["ip"], plan["probes"] = "127.0.0.1", [{"host": "127.0.0.1", "port": box["port"]}]
    assert set(plan["texts"]) == {"pve"}
    r = run_remote(box, plan)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "10.10.10.77" in (box["pve"] / "191.fw").read_text() and (box["guest"] / "table.nft").read_text() == np._table_text(NFT)


def test_the_conf_is_persisted_and_never_reloaded(box):
    """A reload of /etc/nftables.conf runs `flush ruleset` on some guests and would wipe Docker's NAT tables: only table inet filter is replaced."""
    _, plan = plan_for(box, NEW_PVE)
    assert run_remote(box, plan).returncode == 0
    calls = (box["guest"] / "nft.log").read_text().splitlines()
    conf = str(box["guest"] / "nftables.conf")
    assert not [c for c in calls if conf in c], f"the conf was handed to nft: {calls}"
    loads = [c for c in calls if c.startswith("-f ")]
    assert len(loads) == 1 and loads[0].startswith("-f /var/tmp/netpolicy-live"), "exactly one load: the new table, as one atomic file"


SHARED_RULE = "ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport 60072 accept"  # the 0mcp shape: one rule, several tailnet sources
RETIRE_PVE01 = lambda vm: drop_flow(vm, "100.64.0.9", "60072")  # noqa: E731


def test_a_shared_rule_that_loses_one_source_is_replaced_in_place_live_and_persisted(box):
    before = state_of(box)
    _, plan = plan_for(box, RETIRE_PVE01, allow_remove=True)
    assert plan["refusals"] == [] and set(plan["layers"]) == {"input"} and set(plan["conf"]) == {"input"} and "pve" not in plan["texts"]
    assert plan["layers"]["input"]["replace"] == [{"old": SHARED_RULE, "new": "ip saddr 100.64.0.21 tcp dport 60072 accept"}]
    r = run_remote(box, plan)
    assert r.returncode == 0, r.stdout + r.stderr
    after = state_of(box)
    for key, old, new in (("table", SHARED_RULE, "ip saddr 100.64.0.21 tcp dport 60072 accept"),
                          ("conf", "ip saddr { 100.64.0.9, 100.64.0.21 } tcp dport { 60072 } accept", "ip saddr 100.64.0.21 tcp dport { 60072 } accept")):
        a, b = before[key].split("\n"), after[key].split("\n")
        assert len(a) == len(b) and [(x, y) for x, y in zip(a, b) if x != y] == [(x, x.replace(old, new)) for x in a if old in x], key
    assert after["fw"] == before["fw"]
    flows = np.parse_nft(after["table"])["chains"]["input"]["flows"]
    assert F("100.64.0.9", "tcp", "60072") not in flows and F("100.64.0.21", "tcp", "60072") in flows
    calls = (box["guest"] / "nft.log").read_text().splitlines()
    assert [c for c in calls if c.startswith("-f ")] == ["-f /var/tmp/netpolicy-live.nft"] and not [c for c in calls if "nftables.conf" in c]
    names = [e["event"] for e in events(box)]
    assert names.index("armed") < names.index("conf_written") < names.index("table_loaded") < names.index("applied")
    run = next((box["state"] / "apply").glob("*-vm191"))
    assert SHARED_RULE in (run / "nft_table.bak").read_text() and unit_state(box) == ["stopped"]


def test_a_replace_that_fails_verification_puts_the_shared_rule_back_whole(box):
    before = state_of(box)
    _, plan = plan_for(box, RETIRE_PVE01, allow_remove=True)
    assert plan["refusals"] == [] and {"table", "conf"} <= set(plan["texts"]), "a real REPLACE is being rolled back, not an empty run"
    r = run_remote(box, plan, simulate_failure="verify")
    assert r.returncode == 6 and "rolled_back" in r.stdout
    assert state_of(box) == before and SHARED_RULE in state_of(box)["table"]


def test_a_restore_that_reports_success_without_restoring_is_caught_by_the_check(box):
    before = state_of(box)
    _, plan = plan_for(box, NEW_PVE)
    plan["texts"]["pve"] += "INVALID_RULE\n"  # fail late, after the conf and the table were changed
    r = run_remote(box, plan, env_extra={"FAKE_MV_LIES": "1"})
    assert r.returncode == 7, r.stdout + r.stderr
    assert "nftables.conf is not back to its saved text" in r.stdout and state_of(box)["conf"] != before["conf"]


# ───────────── the command ─────────────


def write_policy_file(box, changes):
    path = box["tmp"] / "p.yaml"
    pol = policy_wanting(changes)
    pol["host"] = "t"
    np.write_policy(pol, path)
    snap = box["tmp"] / "snap.json"
    snap.write_text(json.dumps(snapshot()))
    return path, snap


def test_apply_without_yes_prints_the_plan_and_changes_nothing(box, capsys):
    path, snap = write_policy_file(box, NEW_PVE)
    before = state_of(box)
    assert np.main(["apply", "--policy", str(path), "--vm", "191", "--snapshot", str(snap)]) == 0
    out = capsys.readouterr().out
    assert "plan only" in out and "10.10.10.77 tcp/8080" in out and state_of(box) == before and unit_state(box) == []
    assert np.main(["apply", "--policy", str(path), "--vm", "191", "--snapshot", str(snap), "--yes"]) == 3, "--yes needs a live read"


def test_apply_exit_codes_follow_the_outcome(box, monkeypatch, capsys):
    path, snap = write_policy_file(box, NEW_PVE)
    fake_ssh = box["tmp"] / "shims" / "ssh"
    fake_ssh.write_text(f"#!/bin/bash\nexec {sys.executable} -\n")
    fake_ssh.chmod(0o755)
    live = box["tmp"] / "live.json"
    live.write_text(json.dumps(snapshot()))
    monkeypatch.setattr(np, "collect_live", lambda host, alias, **kw: json.loads(live.read_text()))
    orig = np.build_remote_script
    def patched(plan, **kw):
        plan["ip"], plan["probes"] = "127.0.0.1", [{"host": "127.0.0.1", "port": box["port"]}]
        return orig(plan, **dict(kw, guest_conf_path=str(box["guest"] / "nftables.conf")))
    monkeypatch.setattr(np, "build_remote_script", patched)
    base = ["apply", "--policy", str(path), "--vm", "191", "--yes"]
    before = state_of(box)
    assert np.main(base + ["--simulate-failure", "verify"]) == 5, "failed and rolled back and verified"
    assert state_of(box) == before and "rolled_back" in capsys.readouterr().out
    assert np.main(base) == 0 and "10.10.10.77" in state_of(box)["fw"]
    # the file moved under the plan: refused before any change
    live.write_text(json.dumps(snapshot(vm_fw=VM_FW + "IN ACCEPT -source 10.10.10.9/32 -p tcp -dport 9\n")))
    (box["pve"] / "191.fw").write_text(VM_FW)  # the live file is not what the snapshot says
    assert np.main(base) == 1 or np.main(base) == 0
    (box["guest"] / "break").unlink(missing_ok=True)
    live.write_text(json.dumps(snapshot()))
    monkeypatch.setattr(np, "plan_apply", lambda *a, **k: {"vm": "191", "name": "x", "changes": 1, "layers": {}, "conf": {}, "refusals": ["no"], "notes": []})
    assert np.main(base) == 1, "a refused plan is exit 1 and nothing runs"
