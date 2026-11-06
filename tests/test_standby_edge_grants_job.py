"""scripts/standby_edge_grants_job.py: the hourly CT108 job that turns a standby-edge backend port that stays closed into a policy PR the reconciler applies.

Pinned: what it may grant by itself (pool runtimes only, pool port ranges, not the never list or a management port, closed for two runs, listening, not already granted explicitly), that more than 40
ports in one run changes nothing, that its output is classified `additive` by the RECONCILER'S OWN classify() AGAINST THE LIVE POLICY and holds exactly its own grants and tests (and that it waits while
main is not applied yet), that nothing but additions is ever written (every old line survives in order, also on a policy that already holds earlier blocks of the job: the repo's CI runs these very tests
on the job's own PR), that the PR flow merges only when BOTH Woodpecker contexts are green and closes its PR on every failure, that every attempt is on record before the PR flow starts (a red CI is one attempt and
a growing wait, never a PR an hour), that a broken gh or git is found before anything is created, that a kill switch wins during the CI wait, that it runs only installed copies that equal main, and that stale,
failed, non-numeric or foreign input, a paused job, a stale or a fresh open auto PR and a damaged state file each do the right thing.
Prometheus, ssh, gh, Tailscale and the live-policy API are played by fakes; git is real (a local bare origin).
"""
import contextlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from policy_test_sources import source_bytes

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


job = load("standby_edge_grants_job", SCRIPTS / "standby_edge_grants_job.py")
seg = load("standby_edge_grants", SCRIPTS / "standby_edge_grants.py")
sync = load("tailscale_policy_sync", SCRIPTS / "tailscale_policy_sync.py")
rec = load("tailscale_policy_reconcile", SCRIPTS / "tailscale_policy_reconcile.py")

PRIVATE_POLICY = ROOT / "config" / "tailscale" / "policy.hujson"
BASE_POLICY_TEXT = source_bytes(ROOT, "config/tailscale/policy.hujson").decode()
GUARD_PATH = ROOT / "config" / "tailscale" / "lockout-guard.json"
INFER, RGEN, DB, OWN = "100.64.0.24", "100.102.176.103", "100.84.14.14", "100.120.149.126"
# DB is the retired 0database runtime (pve01, cancelled 2026-10-22): no longer a destination, so the job must never grant to its address
T0 = 1_792_400_000


def grown(text, n, first_port=8970):
    """The policy as it is after n earlier job PRs were merged: the job's own insertion applied n times (ports the real policy does not grant)."""
    assert not any(p in job.explicit_grants(sync.parse_hujson(text)).get(INFER, set()) for p in range(first_port, first_port + n))
    for i in range(n):
        gb, tb, _, _ = job.build_blocks({INFER: [first_port + i]}, seg)
        text = job.insert_blocks(text, gb, tb, "2026-10-19T0%d:20Z" % i)
    return text


# The policy every test starts from: the deployment input when present, otherwise the synthetic fixture; or (TIER0_GRANTS_TEST_GROWN=n, used by the last test of this file) the real one after n job PRs were merged, which is what the job's OWN PR contains
# when CI runs this file on it. Anything below that counts or pins something about the policy must still hold then (the first version of this file did not, and the job's first PR went red).
POLICY_TEXT = grown(BASE_POLICY_TEXT, int(os.environ.get("TIER0_GRANTS_TEST_GROWN", "0")), first_port=8960)


def policy():
    return sync.parse_hujson(POLICY_TEXT)


def guard():
    if PRIVATE_POLICY.exists():
        return sync.load_guard(GUARD_PATH)
    return json.loads(source_bytes(ROOT, "config/tailscale/lockout-guard.json"))


def out(cmd, s="", rc=0, err=""):
    return subprocess.CompletedProcess(cmd, rc, s, err)


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


# ------------------------------------------------------------------------------------------------------------------ pure decisions

def test_a_pair_is_granted_only_when_it_is_allowed_listening_and_not_granted_explicitly():
    granted_port = 18004                                            # explicitly granted to the edge on RGEN by the 2026-10-18 block
    closed = [(INFER, 8999, 2), (INFER, 18999, 2), (INFER, 8006, 2), (INFER, 18340, 2), (INFER, 22, 2), (INFER, 9100, 2),      # ok, ok, management, mesh, ssh, exporter
              ("100.1.2.3", 8100, 2), (RGEN, granted_port, 2), (OWN, 8998, 2), (DB, 8997, 2)]
    listening = {INFER: {8999, 8006, 18340, 22, 9100}, RGEN: {granted_port}, OWN: None}
    res = job.decide(closed, policy(), listening)
    assert res["add"] == {INFER: [8999]}
    reasons = {(ip, p): why for ip, p, why in res["rejected"]}
    assert "pool ranges" in reasons[(INFER, 8006)] and "never list" in reasons[(INFER, 18340)] and (INFER, 22) in reasons and (INFER, 9100) in reasons
    assert "not one of the pool runtimes" in reasons[("100.1.2.3", 8100)]
    assert "not one of the pool runtimes" in reasons[(DB, 8997)]                                        # a retired runtime's address is never granted (it can be reused)
    assert [(ip, p) for ip, p, _ in res["stale"]] == [(INFER, 18999)]                                  # nothing listens: a stale pool server is not a grant
    assert [(ip, p) for ip, p, _ in res["unverified"]] == [(OWN, 8998)]                                # the sockets of that host could not be listed: never granted blind
    assert [(ip, p) for ip, p, _ in res["already_granted"]] == [(RGEN, granted_port)]                  # closed although granted: a person looks, no second grant


def test_a_port_covered_only_by_an_older_tag_grant_is_not_counted_as_granted():
    p = {"grants": [{"src": ["100.84.241.55/32"], "dst": ["tag:infer-runtime"], "ip": ["tcp:8999"]}]}
    assert job.explicit_grants(p) == {}                                                                  # tag destinations say nothing about which address; the closed port proves it is not covered
    res = job.decide([(INFER, 8999, 2)], p, {INFER: {8999}})
    assert res["add"] == {INFER: [8999]}


def test_listening_means_reachable_over_the_tailnet_not_bound_to_loopback():
    ss = ("LISTEN 0 4096 0.0.0.0:18301 0.0.0.0:*\nLISTEN 0 4096 [::]:18302 [::]:*\nLISTEN 0 4096 *:18303 *:*\nLISTEN 0 4096 100.64.0.24:18304 0.0.0.0:*\n"
          "LISTEN 0 4096 127.0.0.1:18305 0.0.0.0:*\nLISTEN 0 4096 100.9.9.9:18306 0.0.0.0:*\nLISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:*\n")
    assert job.parse_listening(ss, INFER) == {18301, 18302, 18303, 18304}


def test_a_runtime_whose_sockets_cannot_be_listed_is_unverified_and_never_fails_the_run():
    class Out:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out

    def raising(exc):
        def run(*a, **k):
            raise exc
        return run

    for run in (raising(FileNotFoundError(2, "No such file or directory", "ssh")),                       # no ssh binary on the host
                raising(subprocess.TimeoutExpired("ssh", 90)),                                            # connects, then hangs
                lambda *a, **k: Out(255, ""),                                                             # unreachable
                lambda *a, **k: Out(0, "")):                                                              # reachable, listed nothing
        assert job.listening_ports(INFER, "infer-docker-runtime", run) is None
        res = job.decide([(INFER, 8999, 2)], {"grants": []}, {INFER: job.listening_ports(INFER, "infer-docker-runtime", run)})
        assert res["add"] == {} and [u[:2] for u in res["unverified"]] == [(INFER, 8999)]                # nothing is granted blind
    assert job.listening_ports(INFER, "infer-docker-runtime", lambda *a, **k: Out(0, "LISTEN 0 4096 0.0.0.0:18301 0.0.0.0:*\n")) == {18301}


def test_the_ports_the_job_may_ever_grant_exclude_management_keystore_and_vault_ports():
    assert all(job.allowed_port(p) for p in (3002, 8083, 8999, 18004, 18999))
    assert not any(job.allowed_port(p) for p in (22, 2999, 4000, 8006, 8007, 9100, 18021, 18140, 18340, 19000, 5432))
    assert not any(job.allowed_port(p) for p in (3306, 8200, 8500, 8600, 8888))                       # databases, vault, consul, jupyter sit inside the pool ranges and are never granted by automation
    assert all(job.allowed_port(p) for p in (3002, 3401, 3413, 8300, 8301, 8302))                       # real pool backends (8300-8302 are services of the pools, not consul): still grantable


def test_the_management_ports_are_the_reconcilers_own_so_no_port_can_get_the_whole_batch_refused():
    assert job.MANAGEMENT_PORTS == rec.MANAGEMENT_PORTS                                                 # a drift here would make the guard refuse a batch the job thought fine
    assert not job.allowed_port(3389)                                                                    # RDP sits inside the 3000-3999 pool range
    res = job.decide([(INFER, 3389, 2), (INFER, 8999, 2)], {"grants": []}, {INFER: {3389, 8999}})
    assert res["add"] == {INFER: [8999]} and [r[:2] for r in res["rejected"]] == [(INFER, 3389)]         # the one bad port is rejected, the rest of the batch goes on


def test_a_range_in_the_policy_is_never_expanded_beyond_the_valid_ports():
    t = time.time()
    assert job.parse_ports(["tcp:1-10000000", "tcp:0-5", "tcp:9-3", "tcp:99999999999999999999", "tcp:8000-8002", "udp:1-3", "tcp:70000", 5, None, "tcp:1-65536"]) == {8000, 8001, 8002}
    assert time.time() - t < 1                                                                           # tcp:1-10000000 once cost 1.5 GB and half a minute
    assert len(job.parse_ports(["tcp:1-65535"])) == 65535
    p = {"grants": [{"src": ["100.84.241.55/32"], "dst": [INFER + "/32"], "ip": ["tcp:1-10000000"]}, "not a grant", {"src": None}]}
    assert job.explicit_grants(p) == {INFER: set()}                                                      # junk in the policy is ignored, never a crash


# ------------------------------------------------------------------------------------------------------------------ the policy edit

def additions(add, base=POLICY_TEXT):
    gb, tb, grants, tests = job.build_blocks(add, seg)
    new = job.insert_blocks(base, gb, tb, "2026-10-19T03:20Z")
    return new, grants, tests


@pytest.mark.parametrize("earlier_prs", [0, 1, 3])
def test_new_blocks_go_above_the_end_markers_and_every_old_line_survives_in_order(earlier_prs):
    base = grown(POLICY_TEXT, earlier_prs)                                                               # the policy AFTER earlier job PRs: this very test ran red on the job's own first PR
    new, grants, tests = additions({INFER: [8998, 8999], OWN: [8997]}, base)
    old_lines, new_lines = base.splitlines(), new.splitlines()
    it = iter(new_lines)
    assert all(any(l == n for n in it) for l in old_lines), "an existing line was changed or reordered"           # a subsequence: additions only
    assert new.index('"tcp:8998-8999"') < new.index(job.GRANTS_END) < new.index(job.TESTS_END)
    assert new.count("auto: new standby edge grants") == base.count("auto: new standby edge grants") + 1
    assert new.count("auto: tests of the grants above") == base.count("auto: tests of the grants above") + 1
    assert base.count("auto: new standby edge grants") == POLICY_TEXT.count("auto: new standby edge grants") + earlier_prs


@pytest.mark.parametrize("earlier_prs", [0, 2])
def test_the_reconcilers_own_classify_and_guard_accept_what_the_job_writes(earlier_prs):
    base = grown(POLICY_TEXT, earlier_prs)
    new, grants, tests = additions({INFER: [8998, 8999], OWN: [8997], RGEN: [8996]}, base)
    d = rec.classify(base, new, guard())
    assert d.kind == "additive", d.reasons                                                                       # the unattended reconciler will apply it
    assert d.added_grants == 3 and d.added_tests == 3
    for g in grants:
        assert rec.grant_errors(g, {}) == [] and rec.coverage_errors(g, tests) == []


def test_a_modification_would_be_blocked_by_the_reconciler_which_is_why_the_job_never_edits_a_grant():
    edited = POLICY_TEXT.replace('"tcp:8331", "tcp:18004", "tcp:18006", "tcp:18024", "tcp:18257"', '"tcp:8331", "tcp:18004", "tcp:18006", "tcp:18024", "tcp:18257", "tcp:8990"', 1)
    assert edited != POLICY_TEXT
    assert rec.classify(POLICY_TEXT, edited, guard()).kind == "blocked"


def test_missing_or_duplicated_markers_stop_the_edit():
    for bad in (POLICY_TEXT.replace(job.GRANTS_END, "// moved", 1), POLICY_TEXT + "\n" + job.TESTS_END):
        with pytest.raises(job.CouldNotRun):
            job.insert_blocks(bad, "g", "t", "stamp")


def test_the_generated_text_is_the_form_tailscale_stores_so_the_reconciler_never_sees_a_whitespace_difference():
    gb, tb, grants, tests = job.build_blocks({INFER: [8999]}, seg)
    assert gb.splitlines()[1:4] == ['\t\t\t"src": ["100.84.241.55/32"],', '\t\t\t"dst": ["100.64.0.24/32"],', '\t\t\t"ip":  ["tcp:8999"],']
    assert tb == seg.hujson(tests)


def test_a_policy_with_a_key_twice_in_one_object_is_not_built_on():
    assert job.strict_parse(sync, POLICY_TEXT)["grants"]                                                 # the real policy has none
    for bad in ('{"grants": [], "grants": []}', '{"a": {"b": 1, "b": 2}}', '{"x": [{"k": 1, "k": 1}]}'):
        with pytest.raises(job.Refusal, match="duplicate key"):
            job.strict_parse(sync, bad)
    with pytest.raises(job.CouldNotRun):
        job.strict_parse(sync, "{not json")


# ------------------------------------------------------------------------------------------------------------------ input from Prometheus

def prom_doc(result):
    return json.dumps({"status": "success", "data": {"result": result}})


def prom_with(ok, age, closed=(), queries=None):
    def run(cmd, **kw):
        q = [c for c in cmd if c.startswith("query=")][0][6:]
        if queries is not None:
            queries.append(q)
        if q.startswith("min(tier0_runner_edge_compat_ok"):
            return out(cmd, prom_doc([{"value": [0, ok]}]))
        if q.startswith("time() - max("):
            return out(cmd, prom_doc([{"value": [0, age]}]))
        res = [{"metric": {"backend_ip": ip, "backend_port": str(p)}, "value": [0, str(s)]} for ip, p, s in closed]
        return out(cmd, prom_doc(res))
    return run


def test_all_three_queries_name_the_runners_job_and_role_so_no_other_scraped_target_can_speak_for_it():
    qs = []
    assert job.read_closed("http://p", None, 0, prom_with("1", "600", [(INFER, 8999, 2)], qs)) == [(INFER, 8999, 2)]
    sel = '{job="tier0_node_exporter",role="tier0"}'
    assert qs == ["min(tier0_runner_edge_compat_ok%s)" % sel,
                  "time() - max(tier0_runner_edge_compat_last_success_timestamp_seconds%s)" % sel,
                  "tier0_runner_edge_backend_closed_streak%s >= 2" % sel]


@pytest.mark.parametrize("age", ["NaN", "-86400", "-Inf", "+Inf", "11000", "abc", ""])
def test_an_age_that_is_not_a_plain_fresh_number_is_never_trusted(age):
    with pytest.raises(job.CouldNotRun, match="cannot be trusted"):
        job.read_closed("http://p", None, 0, prom_with("1", age, [(INFER, 8999, 2)]))
    assert job.read_closed("http://p", None, 0, prom_with("1", "0", [(INFER, 8999, 2)])) == [(INFER, 8999, 2)]            # fresh this second is fine


@pytest.mark.parametrize("ok", ["0", "NaN", "+Inf", "2", "x"])
def test_a_check_that_is_not_exactly_ok_is_never_trusted(ok):
    with pytest.raises(job.CouldNotRun, match="cannot be trusted"):
        job.read_closed("http://p", None, 0, prom_with(ok, "60", [(INFER, 8999, 2)]))


def test_a_hostile_streak_or_label_is_skipped_never_a_crash_and_never_a_grant():
    closed = [(INFER, 8999, "+Inf"), (INFER, 8998, "NaN"), (INFER, 8997, "-5"), (INFER, 8996, "1"), (INFER, 8995, 2), (INFER, 8994, "3.9")]
    got = job.read_closed("http://p", None, 0, prom_with("1", "60", closed))
    assert got == [(INFER, 8994, 3), (INFER, 8995, 2)]
    assert job.read_closed("http://p", None, 0, prom_with("1", "60", [(INFER, 8999, 10 ** 9)])) == [(INFER, 8999, 1_000_000)]
    odd = [{"metric": {"backend_ip": ip, "backend_port": port}, "value": [0, "3"]} for ip, port in
           [(INFER, "８０８０"), (INFER, "8_999"), (INFER, " 8998 "), (INFER, "-1"), (INFER, "123456"), ("100.64.0.24 ", "8995"), ("tag:x", "8994"), (INFER, "8993")]]
    odd += [{"metric": {"backend_ip": INFER}, "value": [0, "3"]}, {"value": [0, "3"]}, {"metric": {"backend_ip": INFER, "backend_port": "8992"}, "value": []}, "junk"]

    def run(cmd, **kw):
        q = [c for c in cmd if c.startswith("query=")][0][6:]
        if q.startswith("min("):
            return out(cmd, prom_doc([{"value": [0, "1"]}]))
        if q.startswith("time()"):
            return out(cmd, prom_doc([{"value": [0, "60"]}]))
        return out(cmd, prom_doc(odd))
    assert job.read_closed("http://p", None, 0, run) == [(INFER, 8993, 3)]                                   # only plain ASCII digits and a dotted quad survive


def test_prometheus_answers_that_are_not_answers_are_could_not_run_not_a_traceback():
    for bad in ("", "not json", "[]", '{"status": "error"}', '{"status": "success"}', '{"status": "success", "data": {"result": "x"}}'):
        with pytest.raises(job.CouldNotRun):
            job.read_closed("http://p", None, 0, lambda cmd, **kw: out(cmd, bad))

    def boom(cmd, **kw):
        raise FileNotFoundError("curl")
    with pytest.raises(job.CouldNotRun):
        job.read_closed("http://p", None, 0, boom)
    with pytest.raises(job.CouldNotRun, match="absent"):
        job.read_closed("http://p", None, 0, lambda cmd, **kw: out(cmd, prom_doc([])))


# ------------------------------------------------------------------------------------------------------------------ the whole job with fakes

class FakeAPI:
    """The Tailscale API the job logs in to (the reconciler's TailscaleAPI): the live policy and Tailscale's validate (every policy test)."""

    def __init__(self, live_text, valid=True):
        self.live_text, self.valid, self.validated = live_text, valid, []

    def get_policy(self):
        return self.live_text, '"etag-1"'

    def validate(self, text):
        self.validated.append(text)
        return (True, "valid; policy tests pass") if self.valid else (False, "HTTP 400: a policy test fails")


HELP_WITH_JSON = "USAGE\n  gh pr checks [<number>] [flags]\n\nFLAGS\n      --json fields   Output JSON with the specified fields\n"


class World:
    """Prometheus, ssh, gh, the live plan and Tailscale, played; git is real against a local bare origin (the clone is what the wrapper hands the job: main)."""

    SEED = ("scripts/standby_edge_grants.py", "scripts/standby_edge_grants_job.py", "scripts/tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py",
            "config/tailscale/policy.hujson", "config/tailscale/lockout-guard.json")

    def __init__(self, tmp, closed=((INFER, 8999, 2),), listening=None, ok=1, age=600, ci="pass", open_prs=(), live_text=None, main_text=None, api_valid=True,
                 gh_json=True, gh_push=True, git_push=True, merge_fails=False, checks=None):
        self.tmp = tmp
        self.calls = []
        self.queries = []
        self.closed, self.ok, self.age, self.ci, self.open_prs = closed, ok, age, ci, list(open_prs)
        self.gh_json, self.gh_push, self.git_push, self.merge_fails, self.checks = gh_json, gh_push, git_push, merge_fails, checks
        self.listening = listening if listening is not None else {INFER: "LISTEN 0 4096 0.0.0.0:8999 0.0.0.0:*\n", RGEN: "", OWN: ""}
        self.merged, self.closed_prs, self.close_cmds = [], [], []
        self.on_checks = None
        self.origin = tmp / "origin.git"
        work = tmp / "seed"
        subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
        for rel in self.SEED:
            dst = work / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(source_bytes(ROOT, rel))
        (work / "config/tailscale/policy.hujson").write_text(POLICY_TEXT if main_text is None else main_text)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "-C", str(work), "add", "--"] + list(self.SEED), check=True, env=env)
        subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True, env=env)
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(self.origin)], check=True)
        self.repo = tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)], check=True, env=env)
        self.env = env
        self.lib = tmp / "lib"                                    # the installed copies: the reconciler's tools (equal to main, as the installers keep them)
        self.lib.mkdir()
        for name, rel in (("tailscale_policy_sync.py", "scripts/tailscale_policy_sync.py"), ("tailscale_policy_reconcile.py", "scripts/tailscale_policy_reconcile.py"),
                          ("lockout-guard.json", "config/tailscale/lockout-guard.json")):
            (self.lib / name).write_bytes(source_bytes(ROOT, rel))
        self.rstate = tmp / "reconciler-state"
        self.api = FakeAPI(POLICY_TEXT if live_text is None else live_text, api_valid)

    def run(self, cmd, **kw):
        self.calls.append(list(cmd))
        res = lambda s="", rc=0, err="": out(cmd, s, rc, err)
        if cmd[0] == "curl":
            q = [c for c in cmd if c.startswith("query=")][0][6:]
            self.queries.append(q)
            if q.startswith("min(tier0_runner_edge_compat_ok"):
                return out(cmd, prom_doc([{"value": [0, str(self.ok)]}]))
            if q.startswith("time() - max(tier0_runner_edge_compat_last_success"):
                return out(cmd, prom_doc([{"value": [0, str(self.age)]}]))
            if q.startswith("tier0_runner_edge_backend_closed_streak"):
                return out(cmd, prom_doc([{"metric": {"backend_ip": ip, "backend_port": str(p)}, "value": [0, str(s)]} for ip, p, s in self.closed]))
        if cmd[0] == "ssh":
            alias = cmd[-2]
            ip = {v: k for k, v in job.DESTINATIONS.items()}[alias]
            txt = self.listening.get(ip)
            return res(txt, rc=0 if txt else 255)
        if cmd[0] == "gh":
            sub = cmd[1:3]
            if sub == ["pr", "checks"] and "--help" in cmd:
                return res(HELP_WITH_JSON if self.gh_json else "USAGE\n  gh pr checks [<number>] [flags]\n")
            if cmd[1] == "api":
                return res("true\n" if self.gh_push else "false\n")
            if sub == ["pr", "list"]:
                return res(json.dumps(self.open_prs))
            if sub == ["pr", "create"]:
                return res("https://github.com/x/y/pull/7\n")
            if sub == ["pr", "checks"]:
                if self.on_checks:
                    self.on_checks()
                checks = self.checks if self.checks is not None else [{"name": n, "bucket": self.ci} for n in job.REQUIRED_CHECKS]
                return res(json.dumps(checks))
            if sub == ["pr", "merge"]:
                if self.merge_fails:
                    return res("", 1, "GraphQL: Pull Request is not mergeable (mergePullRequest)")
                self.merged.append(cmd[3])
                return res()
            if sub == ["pr", "close"]:
                self.closed_prs.append(cmd[3])
                self.close_cmds.append(list(cmd))
                return res()
        if cmd[0] == "git":
            if cmd[1:3] == ["push", "--dry-run"] and not self.git_push:
                return res("", 128, "fatal: Authentication failed for 'https://github.com/x/y.git/'")
            return subprocess.run(cmd, env=self.env, **kw)
        raise AssertionError("unexpected command %r" % (cmd,))

    def args(self, **over):
        ns = dict(repo=str(self.repo), slug="x/y", state=str(self.tmp / "state"), lib=str(self.lib), reconciler_state=str(self.rstate), textfile=str(self.tmp / "grants.prom"),
                  prom="http://prom", proxy="127.0.0.1:1055", inject=None, dry_run=False, rehearse=False)
        ns.update(over)
        return type("A", (), ns)

    def go(self, now=T0, advance=0, api_login=None, **over):
        buf = io.StringIO()
        ticks = [now]

        def clock():
            ticks[0] += advance
            return ticks[0]
        with contextlib.redirect_stdout(buf):
            rc = job.run_job(self.args(**over), run=self.run, sleep=lambda s: None, clock=clock,
                             listing=lambda ip, alias, run: job.parse_listening(self.listening[ip], ip) if self.listening.get(ip) else None,
                             api_login=api_login or (lambda: self.api))
        res = [json.loads(l[len("RESULT_JSON "):]) for l in buf.getvalue().splitlines() if l.startswith("RESULT_JSON ")][-1]
        return rc, res

    def prom(self):
        return dict(l.split(" ", 1) for l in (self.tmp / "grants.prom").read_text().splitlines())

    def state(self, name="state.json"):
        p = self.tmp / "state" / name
        return json.load(open(p)) if p.exists() else None

    def created(self):
        return sum(1 for c in self.calls if c[:3] == ["gh", "pr", "create"])

    def branches(self):
        return subprocess.run(["git", "-C", str(self.origin), "branch", "--list", job.BRANCH_PREFIX + "*"], capture_output=True, text=True).stdout.split()

    def pushed_policy(self):
        branches = self.branches()
        assert branches, "no branch was pushed"
        return subprocess.run(["git", "-C", str(self.origin), "show", branches[-1] + ":config/tailscale/policy.hujson"], capture_output=True, text=True).stdout

    def pause(self, which="job"):
        p = (self.tmp / "state" / "PAUSE") if which == "job" else (self.rstate / "reconcile" / "PAUSE")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")


def test_a_port_closed_for_two_runs_and_listening_becomes_a_merged_pr_with_additions_only(tmp_path):
    w = World(tmp_path)
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7" and res["add"] == {INFER: [8999]}, res
    assert w.merged == ["7"] and not w.closed_prs
    new = w.pushed_policy()
    assert '"dst": ["100.64.0.24/32"],' in new and '"tcp:8999"' in new and "100.64.0.24:8999" in new
    assert rec.classify(POLICY_TEXT, new, guard()).kind == "additive"
    assert w.api.validated == [new]                                                                      # Tailscale validated exactly the text that was merged (every policy test)
    m = w.prom()
    assert m["tier0_edge_grants_ok"] == "1" and m["tier0_edge_grants_candidates"] == "1" and m["tier0_edge_grants_prs_total"] == "1" and "tier0_edge_grants_last_success_timestamp_seconds" in m
    assert m["tier0_edge_grants_attempts_total"] == "1" and m["tier0_edge_grants_consecutive_failures"] == "0" and m["tier0_edge_grants_installed_matches_git"] == "1"
    st = w.state()
    assert st["attempts_today"] == 1 and st["prs_total"] == 1 and st["failures"] == 0 and st["last_pr"] == 7 and st["last_attempt_ts"] == T0
    branch = w.branches()[-1]
    files = subprocess.run(["git", "-C", str(w.origin), "show", "--name-only", "--format=", branch], capture_output=True, text=True).stdout.split()
    assert files == ["config/tailscale/policy.hujson"]                                                  # the commit holds the policy file and nothing else
    commit = subprocess.run(["git", "-C", str(w.origin), "log", "-1", "--format=%B", branch], capture_output=True, text=True).stdout
    assert "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" in commit


def test_a_second_job_pr_on_top_of_the_first_one_is_still_additive_and_merges(tmp_path):
    w = World(tmp_path, main_text=grown(POLICY_TEXT, 1), live_text=grown(POLICY_TEXT, 1))                 # the second job PR: main and live already hold the first one
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7", res
    new = w.pushed_policy()
    assert new.count("auto: new standby edge grants") == POLICY_TEXT.count("auto: new standby edge grants") + 2 and rec.classify(grown(POLICY_TEXT, 1), new, guard()).kind == "additive"


def test_nothing_to_grant_changes_nothing_and_still_reports_success(tmp_path):
    w = World(tmp_path, closed=())
    rc, res = w.go()
    assert rc == 0 and res["status"] == "nothing to grant" and not w.merged and w.prom()["tier0_edge_grants_ok"] == "1"
    assert w.state() is None                                                                             # no attempt, no state


def test_more_than_forty_new_ports_in_one_run_refuses_and_says_so_in_the_metrics(tmp_path):
    already = job.explicit_grants(policy()).get(INFER, set())
    ports = [p for p in range(8100, 9000) if p not in already][:41]                                    # 41 ports that really are new (some in this range are granted already)
    assert len(ports) == 41
    w = World(tmp_path, closed=[(INFER, p, 2) for p in ports], listening={INFER: "".join("LISTEN 0 4096 0.0.0.0:%d 0.0.0.0:*\n" % p for p in ports), RGEN: "", OWN: ""})
    rc, res = w.go()
    assert rc == 4 and res["status"] == "refused" and "41 new ports" in res["refused"] and not w.merged
    assert w.prom()["tier0_edge_grants_capped"] == "1" and w.prom()["tier0_edge_grants_ok"] == "0"


def test_an_edge_whose_tailnet_is_down_shows_everything_closed_and_the_cap_catches_it(tmp_path):
    allp = list(range(8200, 8200 + 120))
    w = World(tmp_path, closed=[(INFER, p, 3) for p in allp], listening={INFER: "".join("LISTEN 0 4096 0.0.0.0:%d 0.0.0.0:*\n" % p for p in allp), RGEN: "", OWN: ""})
    rc, res = w.go()
    assert rc == 4 and not w.merged


def test_stale_or_failed_input_is_not_acted_on(tmp_path):
    for i, kw in enumerate((dict(ok=0), dict(age=4 * 3600), dict(age=-600), dict(ok="NaN"))):
        (tmp_path / ("w%d" % i)).mkdir()
        w = World(tmp_path / ("w%d" % i), **kw)
        rc, res = w.go()
        assert rc == 3 and "cannot be trusted" in res["could_not_run"] and not w.merged


# ------------------------------------------------------------------------------------------------------------------ the PR flow: CI, failures, flood, kill switches

def ticking(step):
    t = [0]

    def clock():
        t[0] += step
        return t[0]
    return clock


def checks_run(*sequence):
    """gh pr checks answers one list of (name, bucket) per call; the last one repeats."""
    seq = list(sequence)

    def run(cmd, **kw):
        cur = seq.pop(0) if len(seq) > 1 else seq[0]
        return out(cmd, json.dumps([{"name": n, "bucket": b} for n, b in cur]))
    return run


def wait(run, limit=600):
    return job.wait_ci("x/y", 7, run=run, sleep=lambda s: None, clock=ticking(30), limit=limit)


def test_ci_is_green_only_when_both_woodpecker_contexts_have_passed():
    pr, push = job.REQUIRED_CHECKS
    assert pr == "ci/woodpecker/pr/woodpecker" and push == "ci/woodpecker/push/woodpecker"             # the names GitHub shows on a PR of this repository
    assert wait(checks_run([("some-bot/lint", "pass")])) is None                                         # an unrelated fast check is not CI (the old code merged on it)
    assert wait(checks_run([(pr, "pass")])) is None                                                      # the push pipeline has not reported yet
    assert wait(checks_run([(pr, "pass"), (push, "pending")], [(pr, "pass"), (push, "pending")], [(pr, "pass"), (push, "pass")])) is True
    assert wait(checks_run([(pr, "pass"), (push, "pass"), ("ci/woodpecker/pull_request_closed/woodpecker", "pass"), ("x", "skipping")])) is True
    assert wait(checks_run([(pr, "pass"), (push, "skipping")])) is None                                  # a skipped required context is not a pass
    assert wait(checks_run([(pr, "pass"), (push, "pass"), (push, "fail")])) is False                     # any failure of a re-run context counts
    assert wait(checks_run([("x", "fail")])) is False                                                    # a failure anywhere is a stop before the others have reported
    assert wait(checks_run([(pr, "pass"), (push, "cancel")])) is False
    assert wait(lambda cmd, **kw: out(cmd, "not json")) is None and wait(lambda cmd, **kw: out(cmd, "{}")) is None


def test_ci_that_fails_closes_the_pr_and_merges_nothing(tmp_path):
    w = World(tmp_path, ci="fail")
    rc, res = w.go()
    assert rc == 5 and res["status"] == "PR flow failed" and w.closed_prs == ["7"] and not w.merged
    assert "--delete-branch" in w.close_cmds[0] and "CI failed on PR #7" in " ".join(w.close_cmds[0])
    assert w.prom()["tier0_edge_grants_ok"] == "0"
    assert w.state()["failures"] == 1 and w.state()["attempts_today"] == 1                               # the attempt was on record before the PR existed, and so is the failure


def test_ci_that_never_reports_both_contexts_closes_the_pr_in_time(tmp_path):
    w = World(tmp_path, checks=[{"name": "some-bot/lint", "bucket": "pass"}])
    rc, res = w.go(advance=60)                                                                           # a clock that moves: 25 minutes pass in the fake
    assert rc == 5 and w.closed_prs == ["7"] and not w.merged and "no required result in time" in " ".join(w.close_cmds[0])


def test_a_refused_merge_closes_the_pr_instead_of_leaving_it_open(tmp_path):
    w = World(tmp_path, merge_fails=True)
    rc, res = w.go()
    assert rc == 5 and w.closed_prs == ["7"] and not w.merged
    assert w.state()["failures"] == 1


def test_a_commit_that_would_hold_anything_but_the_policy_is_never_made(tmp_path):
    w = World(tmp_path)
    (w.repo / "stray.txt").write_text("x")
    subprocess.run(["git", "-C", str(w.repo), "add", "stray.txt"], check=True, env=w.env)                  # something already staged in the clone: the class of accident `git add -A` is
    rc, res = w.go()
    assert rc == 5 and "staged files are" in res["pr_flow"] and not w.branches() and w.created() == 0
    assert w.state()["failures"] == 1


def test_a_push_that_is_rejected_is_a_recorded_failed_attempt_with_no_pr_and_no_branch(tmp_path):
    w = World(tmp_path)
    hook = w.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    rc, res = w.go()
    assert rc == 5 and w.created() == 0 and not w.branches()
    assert w.state()["attempts_today"] == 1 and w.state()["failures"] == 1


def test_a_red_ci_is_one_attempt_then_a_growing_wait_not_a_pr_every_hour(tmp_path):
    shared = tmp_path / "shared-state"
    prom = tmp_path / "grants.prom"
    creates, log = 0, []
    for hour in range(9):
        d = tmp_path / ("h%d" % hour)
        d.mkdir()
        w = World(d, ci="fail")
        rc, res = w.go(now=T0 + hour * 3600, state=str(shared), textfile=str(prom))
        creates += w.created()
        log.append((hour, rc, res["status"].split(":")[0], dict(l.split(" ", 1) for l in prom.read_text().splitlines())["tier0_edge_grants_ok"]))
    st = json.load(open(shared / "state.json"))
    # hour 0: attempt (red); 1-5: backing off six hours; 6: second attempt (red); 7-8: backing off 18 hours. Before the fix: nine PRs and nine CI runs, state never written.
    assert creates == 2, log
    assert [e[1] for e in log] == [5, 0, 0, 0, 0, 0, 5, 0, 0]
    assert [e[2] for e in log] == ["PR flow failed"] + ["waiting"] * 5 + ["PR flow failed"] + ["waiting"] * 2
    assert all(e[3] == "0" for e in log)                                                                 # ok stays 0 while it backs off: Tier0EdgeGrantsFailed fires, it is not hidden by the wait
    assert st["failures"] == 2 and st["attempts_total"] == 2 and st["attempts_today"] == 2 and st["prs_total"] == 0


def test_a_success_ends_the_backoff(tmp_path):
    (tmp_path / "state").mkdir()
    json.dump({"day": time.strftime("%Y-%m-%d", time.gmtime(T0)), "attempts_today": 1, "last_attempt_ts": T0 - 7 * 3600, "failures": 1, "attempts_total": 1}, open(tmp_path / "state" / "state.json", "w"))
    w = World(tmp_path)
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7" and w.state()["failures"] == 0 and w.prom()["tier0_edge_grants_consecutive_failures"] == "0"


def test_the_wait_after_failures_triples_up_to_a_day():
    assert [job.wait_between_attempts(n) for n in (0, 1, 2, 3, 4, 9)] == [2 * 3600, 6 * 3600, 18 * 3600, 24 * 3600, 24 * 3600, 24 * 3600]


@pytest.mark.parametrize("kw, why", [(dict(gh_json=False), "pr checks --json"), (dict(gh_push=False), "no push access"), (dict(git_push=False), "git cannot push")])
def test_a_broken_gh_or_git_is_found_before_any_branch_or_pr_exists(tmp_path, kw, why):
    w = World(tmp_path, **kw)
    rc, res = w.go()
    assert rc == 3 and why in res["could_not_run"], res
    assert w.created() == 0 and not w.merged and not w.branches()
    assert w.state() is None                                                                             # it was never an attempt
    assert w.prom()["tier0_edge_grants_ok"] == "0"                                                       # but it is loud, hours before the first real grant needs it
    (tmp_path / "idle").mkdir()
    idle = World(tmp_path / "idle", closed=(), **kw)                                                     # even when there is nothing to grant today
    assert idle.go()[0] == 3


def test_an_open_auto_pr_older_than_two_hours_is_closed_a_fresh_one_is_waited_for(tmp_path):
    branch = job.BRANCH_PREFIX + "20261019T012000Z"
    (tmp_path / "a").mkdir()
    w = World(tmp_path / "a", open_prs=[{"number": 3, "headRefName": branch, "createdAt": iso(T0 - 3 * 3600)}])
    rc, res = w.go()
    assert rc == 5 and "closed 1 stale automatic PR" in res["status"] and w.closed_prs == ["3"] and "--delete-branch" in w.close_cmds[0] and not w.merged
    assert w.state()["failures"] == 1 and w.prom()["tier0_edge_grants_ok"] == "0" and w.created() == 0
    assert any(c[:3] == ["gh", "pr", "list"] and c[c.index("--limit") + 1] == "200" for c in w.calls)     # the default of 30 could miss it
    (tmp_path / "b").mkdir()
    w = World(tmp_path / "b", open_prs=[{"number": 3, "headRefName": branch, "createdAt": iso(T0 - 600)}])
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("a previous auto PR is still open") and not w.closed_prs and not w.merged and w.prom()["tier0_edge_grants_pr_open"] == "1"
    (tmp_path / "c").mkdir()
    w = World(tmp_path / "c", open_prs=[{"number": 3, "headRefName": branch, "createdAt": "x"}, {"number": 4, "headRefName": "someone-elses-branch", "createdAt": "x"}])
    rc, res = w.go()
    assert rc == 5 and w.closed_prs == ["3"]                                                             # an age nobody can read counts as stale; a branch that is not the job's is never touched


def test_a_pause_file_a_paused_reconciler_and_the_daily_limits_each_stop_a_second_pr(tmp_path):
    (tmp_path / "b").mkdir()
    w = World(tmp_path / "b")
    w.pause("job")
    rc, res = w.go()
    assert rc == 0 and res["status"] == "paused" and not w.merged and w.created() == 0
    (tmp_path / "r").mkdir()
    w = World(tmp_path / "r")
    w.pause("reconciler")
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("waiting: the tailnet policy reconciler is paused") and w.created() == 0 and not any(c[0] == "gh" for c in w.calls)
    assert w.prom()["tier0_edge_grants_waiting_reconciler"] == "1" and w.prom()["tier0_edge_grants_ok"] == "1" and w.state() is None
    (tmp_path / "c").mkdir()
    w = World(tmp_path / "c")
    (tmp_path / "c" / "state").mkdir()
    json.dump({"day": time.strftime("%Y-%m-%d", time.gmtime(T0)), "attempts_today": job.MAX_ATTEMPTS_PER_DAY, "last_attempt_ts": 0}, open(tmp_path / "c" / "state" / "state.json", "w"))
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("waiting") and not w.merged and w.created() == 0 and w.prom()["tier0_edge_grants_ok"] == "1"
    (tmp_path / "d").mkdir()
    w = World(tmp_path / "d")
    (tmp_path / "d" / "state").mkdir()
    json.dump({"day": "x", "attempts_today": 0, "last_attempt_ts": T0 - 600}, open(tmp_path / "d" / "state" / "state.json", "w"))
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("waiting") and not w.merged                             # two hours between automatic attempts
    assert job.MAX_ATTEMPTS_PER_DAY < rec.MAX_APPLIES_PER_DAY                                            # the job can never use up every unattended apply the reconciler allows in a day


@pytest.mark.parametrize("which", ["job", "reconciler"])
def test_a_kill_switch_that_appears_during_the_ci_wait_wins_and_the_pr_is_closed(tmp_path, which):
    w = World(tmp_path)
    w.on_checks = lambda: w.pause(which)
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("paused while the PR was open") and w.closed_prs == ["7"] and not w.merged
    assert w.state()["failures"] == 0 and w.state()["attempts_today"] == 1                               # an operator's switch is not a failure, but the attempt happened


def test_a_stop_from_outside_during_the_ci_wait_closes_the_pr_and_is_not_a_failure(tmp_path):
    """The builder is halted every night at 01:30 UTC by its backup (a reboot or systemctl stop looks the same): the unit gets SIGTERM, the job unwinds and closes its PR. That is not the PR flow's fault."""
    w = World(tmp_path)

    def term():
        raise KeyboardInterrupt("terminated by signal 15")
    w.on_checks = term
    rc, res = w.go()
    assert rc == 5 and res["status"].startswith("PR flow interrupted from outside") and res["interrupted"] is True
    assert w.closed_prs == ["7"] and not w.merged and "--delete-branch" in w.close_cmds[0]
    st = w.state()
    assert st["failures"] == 0 and st["attempts_today"] == 1 and st["last_attempt_ts"] == T0           # on record as an attempt (2 a day, 2 h apart), but no growing wait
    assert w.prom()["tier0_edge_grants_consecutive_failures"] == "0"
    (tmp_path / "next").mkdir()
    rc2, res2 = World(tmp_path / "next").go(now=T0 + 2 * 3600 + 60, state=str(tmp_path / "state"))
    assert rc2 == 0 and res2["status"] == "merged PR #7", res2                                           # the first run after the boot, two hours on, goes on at once
    with pytest.raises(KeyboardInterrupt):
        job.terminate(signal.SIGTERM, None)


def test_main_turns_sigterm_into_a_clean_unwind(monkeypatch):
    seen = {}
    monkeypatch.setattr(job, "run_job", lambda a: seen.setdefault("handler", signal.getsignal(signal.SIGTERM)) and 0)
    before = signal.getsignal(signal.SIGTERM)
    try:
        assert job.main(["--repo", "x", "--state", "y", "--dry-run"]) == 0
        assert seen["handler"] is job.terminate
    finally:
        signal.signal(signal.SIGTERM, before)


# ------------------------------------------------------------------------------------------------------------------ judged against the LIVE policy

def test_while_the_reconciler_has_not_applied_main_the_job_adds_nothing_on_top(tmp_path):
    """Three foreign grants merged but not applied + the job's own would be six: the reconciler refuses '> 5 grants' and the old job kept merging on top and ignored its pause."""
    w = World(tmp_path, main_text=grown(POLICY_TEXT, 3), live_text=POLICY_TEXT)
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("waiting: main and the live tailnet policy differ"), res
    assert w.created() == 0 and not w.merged and w.state() is None and not w.api.validated
    assert w.prom()["tier0_edge_grants_waiting_reconciler"] == "1" and w.prom()["tier0_edge_grants_ok"] == "1"


def test_a_live_policy_that_is_ahead_of_main_is_not_built_on_either(tmp_path):
    w = World(tmp_path, main_text=POLICY_TEXT, live_text=grown(POLICY_TEXT, 1))                          # somebody applied a grant by hand: the reconciler is blocked ("removes 1 entries")
    rc, res = w.go()
    assert rc == 0 and res["status"].startswith("waiting") and "removes" in res["waiting"] and w.created() == 0


def test_a_live_policy_that_differs_from_main_in_comments_only_is_still_fine(tmp_path):
    w = World(tmp_path, live_text=POLICY_TEXT.replace("\n", "\n\n", 3))                                  # the reconciler classes it text_only and applies it as it applies anything
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7", res


def test_a_change_that_holds_more_than_the_jobs_own_grants_is_refused(tmp_path, monkeypatch):
    real = job.build_blocks

    def greedy(add, seg_):
        gb, tb, grants, tests = real(add, seg_)
        gb2, tb2, _, _ = real({OWN: [8997]}, seg_)                                                       # a second host's grant slips into the text...
        return gb + "\n" + gb2, tb + "\n" + tb2, grants, tests                                           # ...but is not among the grants the job vouches for
    monkeypatch.setattr(job, "build_blocks", greedy)
    w = World(tmp_path)
    rc, res = w.go()
    assert rc == 4 and "holds more (or less) than the job's own 1 grant(s)" in res["refused"] and "2 grant(s)" in res["refused"] and not w.merged and w.created() == 0


def test_tailscale_rejecting_the_policy_is_a_refusal_not_a_pr(tmp_path):
    w = World(tmp_path, api_valid=False)
    rc, res = w.go()
    assert rc == 4 and "did not pass" in res["refused"] and w.created() == 0 and w.state() is None


def test_a_login_that_fails_is_could_not_run(tmp_path):
    def login():
        raise sys.modules["tailscale_policy_sync"].SyncError("vault credential fetch failed")
    w = World(tmp_path)
    rc, res = w.go(api_login=login)
    assert rc == 3 and "cannot log in to Tailscale" in res["could_not_run"] and w.created() == 0


def test_a_policy_in_main_with_a_duplicate_key_is_refused(tmp_path):
    w = World(tmp_path, main_text=POLICY_TEXT.replace('"tagOwners": {', '"tests": [],\n\t"tagOwners": {', 1))
    rc, res = w.go()
    assert rc == 4 and "duplicate key" in res["refused"] and w.created() == 0


def test_a_plan_with_the_job_and_five_foreign_grants_would_be_blocked_by_the_reconcilers_own_limit(tmp_path, monkeypatch):
    hosts = ["100.77.0.%d" % i for i in range(1, 7)]                                                           # six destination hosts would be six new grants: the reconciler applies at most five per change
    monkeypatch.setattr(job, "DESTINATIONS", {h: "alias-%d" % i for i, h in enumerate(hosts)})
    w = World(tmp_path, closed=[(h, 8999, 2) for h in hosts])
    w.listening = {h: "LISTEN 0 4096 0.0.0.0:8999 0.0.0.0:*\n" for h in hosts}
    rc, res = w.go(dry_run=True)
    assert rc == 4 and "would classify this change as blocked" in res["refused"] and "max 5 per change" in res["refused"], res          # the reconciler's own words: it would not apply it by itself
    assert not w.merged


# ------------------------------------------------------------------------------------------------------------------ what runs is what was reviewed

@pytest.mark.parametrize("where, rel", [("clone", "scripts/tailscale_policy_sync.py"), ("clone", "scripts/tailscale_policy_reconcile.py"), ("clone", "config/tailscale/lockout-guard.json"),
                                        ("clone", "scripts/standby_edge_grants.py"), ("clone", "scripts/standby_edge_grants_job.py"),
                                        ("lib", "tailscale_policy_sync.py"), ("lib", "tailscale_policy_reconcile.py"), ("lib", "lockout-guard.json")])
def test_an_installed_file_that_differs_from_main_runs_nothing_and_a_merge_never_runs_by_itself(tmp_path, where, rel):
    w = World(tmp_path)
    canary = tmp_path / "canary.txt"
    p = (w.repo / rel) if where == "clone" else (w.lib / rel)
    p.write_text(p.read_text() + ("\nopen(%r, 'a').write('executed')\n" % str(canary) if rel.endswith(".py") else "\n "))      # a trailing space: a trailing newline alone is not a difference
    rc, res = w.go()
    assert rc == 3 and "differs from main" in res["could_not_run"], res
    assert not canary.exists() and w.created() == 0 and not any(c[0] in ("gh", "git", "curl") for c in w.calls)         # nothing ran: not the clone's code, not even a query
    m = w.prom()
    assert m["tier0_edge_grants_installed_matches_git"] == "0" and m["tier0_edge_grants_ok"] == "0"


def test_a_missing_installed_copy_is_could_not_run(tmp_path):
    w = World(tmp_path)
    (w.lib / "tailscale_policy_sync.py").unlink()
    rc, res = w.go()
    assert rc == 3 and "installed copy of scripts/tailscale_policy_sync.py is missing" in res["could_not_run"]


def test_line_endings_alone_are_not_a_difference(tmp_path):
    w = World(tmp_path)
    p = w.lib / "lockout-guard.json"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7"


# ------------------------------------------------------------------------------------------------------------------ the state file

@pytest.mark.parametrize("bad", ["[]", "null", "5", '"x"', "{", "",
                                 json.dumps({"last_attempt_ts": T0 + 5 * 365 * 86400, "last_pr_ts": T0 + 5 * 365 * 86400, "attempts_today": "x", "failures": -3, "day": 5, "prs_total": True})])
def test_a_state_file_that_is_not_what_the_job_wrote_never_wedges_it(tmp_path, bad):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "state.json").write_text(bad)
    w = World(tmp_path)
    rc, res = w.go()
    assert rc == 0 and res["status"] == "merged PR #7", res                                              # a clock that was five years ahead once, or a half-written file, holds nothing back


def test_load_state_keeps_what_is_valid(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"day": "2026-10-19", "attempts_today": 1, "last_attempt_ts": T0 - 5, "failures": 2, "prs_total": 3, "last_pr": 9, "last_pr_ts": T0 - 9}))
    assert job.load_state(str(p), T0) == {"day": "2026-10-19", "attempts_today": 1, "last_attempt_ts": T0 - 5, "failures": 2, "prs_total": 3, "last_pr": 9, "last_pr_ts": T0 - 9,
                                          "attempts_total": 0, "last_failure_ts": 0}


# ------------------------------------------------------------------------------------------------------------------ rehearsal and dry run

def test_a_rehearsal_runs_the_whole_pr_flow_but_closes_the_pr_unmerged_and_leaves_no_trace_in_state_or_metrics(tmp_path):
    w = World(tmp_path)
    w.pause("job")                                                                                       # the operator asked for it: the kill switch of the unattended timer does not stop it
    rc, res = w.go(rehearse=True)
    assert rc == 0 and res["status"] == "rehearsal: PR #7 passed CI and was closed unmerged", res
    assert w.created() == 1 and w.closed_prs == ["7"] and not w.merged and "rehearsal" in w.branches()[-1] and "--delete-branch" in w.close_cmds[0]
    create = [c for c in w.calls if c[:3] == ["gh", "pr", "create"]][0]
    assert create[create.index("--title") + 1].startswith("REHEARSAL, closed unmerged")
    assert w.state() is None and not (tmp_path / "grants.prom").exists()
    assert any(c[:3] == ["gh", "pr", "checks"] and "--json" in c for c in w.calls)                       # both contexts were really waited for


def test_a_rehearsal_with_a_red_ci_closes_the_pr_and_still_leaves_no_trace(tmp_path):
    w = World(tmp_path, ci="fail")
    rc, res = w.go(rehearse=True)
    assert rc == 5 and w.closed_prs == ["7"] and not w.merged and w.state() is None and not (tmp_path / "grants.prom").exists()


def test_the_dry_run_computes_everything_and_touches_neither_github_nor_the_state_nor_the_metrics(tmp_path):
    w = World(tmp_path)
    rc, res = w.go(dry_run=True)
    assert rc == 0 and res["status"] == "dry run: would open a PR" and res["add"] == {INFER: [8999]}
    assert not any(c[0] == "gh" for c in w.calls) and not (tmp_path / "grants.prom").exists() and not w.merged
    assert w.api.validated and w.state() is None and not w.branches()                                    # Tailscale was asked (validate is read-only), nothing was written anywhere


def test_the_inject_option_replaces_prometheus_for_drills(tmp_path):
    w = World(tmp_path, ok=0)                                                                                  # a failing check would stop the real input...
    inj = tmp_path / "closed.json"
    inj.write_text(json.dumps([[INFER, 8999, 2]]))
    rc, res = w.go(inject=str(inj), dry_run=True)
    assert rc == 0 and res["add"] == {INFER: [8999]} and not any(c[0] == "curl" for c in w.calls)              # ...an injected list does not talk to Prometheus at all


@pytest.mark.skipif(not PRIVATE_POLICY.exists(), reason="deployment policy is intentionally excluded from the public mirror")
def test_the_real_policy_in_this_repo_has_exactly_one_of_each_marker_and_both_sit_inside_their_arrays():
    from_policy = POLICY_TEXT
    assert from_policy.count(job.GRANTS_END) == 1 and from_policy.count(job.TESTS_END) == 1
    p = sync.parse_hujson(from_policy)
    assert isinstance(p["grants"], list) and isinstance(p["tests"], list)
    assert from_policy.index(job.GRANTS_END) < from_policy.index('"ssh": [') < from_policy.index(job.TESTS_END)


def test_only_pairs_closed_for_two_runs_in_a_row_are_asked_for(tmp_path):
    w = World(tmp_path)
    w.go(dry_run=True)
    sel = '{job="tier0_node_exporter",role="tier0"}'
    assert "tier0_runner_edge_backend_closed_streak%s >= 2" % sel in w.queries                                 # a one-run hiccup (the tailnet of the edge for a minute) never reaches a policy change
    assert job.MIN_STREAK == 2


def test_this_whole_file_passes_on_a_policy_that_already_holds_earlier_job_blocks():
    """The repo's CI runs this very file on the job's own PR, and that PR's policy holds the job's first block. Run the file again on a policy grown by two merged job PRs."""
    if os.environ.get("TIER0_GRANTS_TEST_GROWN"):
        pytest.skip("this is the grown run already")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", "-k", "not this_whole_file_passes", str(Path(__file__))],
                       env=dict(os.environ, TIER0_GRANTS_TEST_GROWN="2"), cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
