#!/usr/bin/env python3
"""tier0-edge-grants: close the loop for the standby edge's tailnet grants (runs hourly on CT108; nobody in the loop).

The standby gateway keeps every production pool's surviving servers, which are tailnet ip:port pairs, and the edge VM (100.84.241.55) may only reach the ports its grants name.
The pools program keeps adding ports; on 2026-10-18 a day of new pools left 103 of 293 ports closed and 92 names answering 504 (docs/runbooks/standby-edge-grants.md). The hourly edge-compat
check on the runner now TCP-tests every pair and the runner exports, per closed pair, how many hourly runs in a row it has been closed (`tier0_runner_edge_backend_closed_streak`).
This job turns a pair that stays closed into a policy change, through the same reviewed path a person uses, and the tailnet policy reconciler applies it:

  1. read the pairs closed for >= 2 runs from the primary Prometheus (read-only API, through the builder's userspace tailscaled), only while the check itself is fresh and ok; the queries name the
     runner's job and role, so no other scraped target can speak for it, and a value that is not a plain finite number is refused
  2. keep only what it may grant by itself: a destination host on the allowlist (the four pool runtimes), a port in the pool port ranges (3000-3999, 8000-8999, 18000-18999) that is not on the
     never list (keystore API/mesh, vault) and not a management port, that is not already granted to the edge explicitly, and that is LISTENING on the destination (ss over ssh; a stale pool
     server is not a grant, and a port nobody listens on today could be another service tomorrow)
  3. more than MAX_NEW_PORTS new ports in one run is an incident or a misconfiguration (an edge whose tailnet is down shows everything closed): nothing is changed and an alert says so
  4. append NEW grants (one per destination host, /32, exact ports) and their policy tests above the END markers of the policy: additions only, never a modification (a modified grant is a
     removal plus an addition, which the reconciler blocks). Everything is judged against the LIVE policy, the one the reconciler compares with: main must already equal it (the job never
     stacks a change on one the reconciler has not applied, and never while the reconciler is paused), the reconciler's own classify() of live -> main+additions must say `additive`, the guard and
     the offline check must pass, Tailscale must validate it (every policy test), and the difference must be EXACTLY the job's own grants and tests: not one more, not one less
  5. branch, commit (the policy file only), PR, wait until BOTH Woodpecker contexts have reported green, look at the kill switches again, squash-merge; the reconciler applies it within ~30 minutes.
     A PR that cannot be merged for any reason (red or silent CI, a refused merge, a kill switch, a signal) is closed with its branch, never left open

What keeps a broken day from becoming a flood: every ATTEMPT (not only a merge) is written to the state file BEFORE the PR flow starts; at most MAX_ATTEMPTS_PER_DAY a day, two hours apart, and after a
failed attempt the wait grows (x3 per consecutive failure, up to a day) while `ok` stays 0 so the alert fires. A run stopped from outside (SIGTERM: the builder is halted every night at 01:30 UTC by
its backup, or a reboot, or systemctl stop) closes its PR and counts as an attempt but not as a failure. An open automatic PR older than two hours (a run that died) is closed.
What keeps unreviewed code out: the code that runs is the INSTALLED copy (the tools next to the reconciler's, this file and standby_edge_grants.py in /usr/local/lib/tier0-edge-grants), never a clone
of main; every installed file must equal main (scripts/tier0-edge-grants-install.sh installs them), otherwise the job runs nothing and `installed_matches_git` is 0.

  standby_edge_grants_job.py --repo CLONE --state DIR [--lib DIR] [--textfile F] [--prom URL --proxy HOST:PORT] [--inject closed.json] [--dry-run | --rehearse]
  --dry-run   compute and validate everything, touch neither GitHub, the state nor the metrics
  --rehearse  the whole PR flow for real (branch, PR, both CI contexts) but the PR is closed instead of merged, no state, no metrics, ignores PAUSE (the operator asked for it): proves a change of this code
Exit: 0 nothing to do / waiting / PR merged / dry run, 3 could not run (no fresh input, clone, Prometheus, gh, installed copies, policy markers), 4 refused (cap exceeded, validation failed: a human
looks), 5 PR flow failed. Never touches anything but the policy file in a PR, never removes or edits an existing grant, never grants a port it has not seen closed twice and listening."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

EDGE_SRC = "100.84.241.55/32"                           # edge-standby-0mcp (VM110), joined as tag:pool-runtime: its outbound access is granted by address
DESTINATIONS = {                                         # tailnet ip -> the builder's ssh alias for that runtime (the aliases keystore-mesh-roll.py uses)
    "100.64.0.24": "infer-docker-runtime",
    "100.102.176.103": "lv3-docker-runtime",
    "100.120.149.126": "own-docker-runtime",
}
PORT_RANGES = ((3000, 3999), (8000, 8999), (18000, 18999))
NEVER_PORTS = {18021, 18140, 18322, 18340, 3128, 5432, 5355, 9090, 9093, 9094, 9100,      # keystore API/mesh, vault, the triage webhook, proxies, databases, exporters: never by automation
               3306, 8200, 8500, 8600, 8888}                                              # well-known ports no pool uses (MySQL, Vault, Consul, Jupyter): the 2026-10-18 measurement has pool backends on 3002/3401/3413, 8xxx (8300-8302 included) and 18xxx only
MANAGEMENT_PORTS = ((22, 23), (135, 139), (445, 445), (2222, 2222), (3389, 3389), (5900, 5999), (5985, 5986), (8006, 8007))   # the reconciler's own list (a test pins that they agree): a port in it would get the whole batch refused
RUNNER = 'job="tier0_node_exporter",role="tier0"'        # the series of the tier-0 runner's node exporter: the only ones the job believes
MIN_STREAK = 2
MAX_NEW_PORTS = 40
MAX_ATTEMPTS_PER_DAY = 2                                 # attempts, not only merges; the reconciler applies at most 3 a day and one stays free for a person's change
MIN_SECONDS_BETWEEN_ATTEMPTS = 2 * 3600
MAX_BACKOFF = 24 * 3600
INPUT_MAX_AGE = 3 * 3600
STALE_PR_SECONDS = 2 * 3600
CI_WAIT_SECONDS = 25 * 60
REQUIRED_CHECKS = ("ci/woodpecker/pr/woodpecker", "ci/woodpecker/push/woodpecker")      # both must have reported and passed: an unrelated fast check is not CI
BRANCH_PREFIX = "tier0-edge-grants-"
GRANTS_END = "// ==== standby-edge-auto-grants END"
TESTS_END = "// ==== standby-edge-auto-grants-tests END"
DEFAULT_LIB = "/usr/local/lib/tailscale-policy-sync"     # where the reconciler's tools are installed (and kept equal to git by the reconciler itself)
HERE = Path(__file__).resolve().parent


class Refusal(Exception):
    """Something a person has to look at: the job changes nothing."""


class CouldNotRun(Exception):
    pass


class Waiting(Exception):
    """Not now: the live policy is behind main (the reconciler has not applied it yet) or something else has to happen first. Not a failure."""


class Paused(Exception):
    """A kill switch appeared while the PR was open."""


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def norm(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def read_json(path):
    with open(path) as f:
        return json.load(f)


def finite(x):
    v = float(x)
    if not math.isfinite(v):
        raise ValueError("not a finite number")
    return v


# ---------------------------------------------------------------------------------------------------------------- input

def prom_query(prom, proxy, query, run=subprocess.run):
    cmd = ["curl", "-s", "-m", "25"]
    if proxy:
        cmd += ["--socks5-hostname", proxy]
    cmd += ["-G", prom.rstrip("/") + "/api/v1/query", "--data-urlencode", "query=" + query]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise CouldNotRun("Prometheus cannot be asked: %s" % type(e).__name__)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        raise CouldNotRun("Prometheus did not answer: " + (r.stderr or r.stdout)[:120])
    if not isinstance(doc, dict) or doc.get("status") != "success":
        raise CouldNotRun("Prometheus query failed: " + str(doc)[:160])
    try:
        result = doc["data"]["result"]
    except (KeyError, TypeError):
        raise CouldNotRun("Prometheus answered without a result")
    if not isinstance(result, list):
        raise CouldNotRun("Prometheus answered without a result list")
    return result


def read_closed(prom, proxy, now, run=subprocess.run):
    """[(ip, port, streak)] closed for MIN_STREAK runs in a row; refuses to act on stale, failed or non-numeric checks."""
    sel = "{" + RUNNER + "}"
    ok = prom_query(prom, proxy, "min(tier0_runner_edge_compat_ok%s)" % sel, run)
    age = prom_query(prom, proxy, "time() - max(tier0_runner_edge_compat_last_success_timestamp_seconds%s)" % sel, run)
    if not ok or not age:
        raise CouldNotRun("the edge-compat metrics are absent")
    try:
        ok_v, age_v = finite(ok[0]["value"][1]), finite(age[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise CouldNotRun("the edge-compat metrics are not plain numbers: the closed list cannot be trusted")
    if ok_v != 1 or not 0 <= age_v <= INPUT_MAX_AGE:                  # a negative age is a timestamp from the future: as untrustworthy as a stale one
        raise CouldNotRun("the hourly edge-compat check is failing or stale (age %.0f s): its closed list cannot be trusted" % age_v)
    out = []
    for x in prom_query(prom, proxy, "tier0_runner_edge_backend_closed_streak%s >= %d" % (sel, MIN_STREAK), run):
        try:
            m = x["metric"]
            ip, port, streak = m["backend_ip"], m["backend_port"], finite(x["value"][1])
            if not re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){3}", ip) or not re.fullmatch(r"[0-9]{1,5}", port) or streak < MIN_STREAK:
                continue
            out.append((ip, int(port), int(min(streak, 1e6))))
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            continue
    return sorted(set(out))


# ---------------------------------------------------------------------------------------------------------------- decisions

def parse_ports(rules):
    """The ports of `tcp:N` / `tcp:A-B` rules; a rule that is not a valid port range is ignored (a range is never expanded beyond 65535 entries)."""
    ports = set()
    for rule in rules:
        m = re.fullmatch(r"tcp:([0-9]{1,5})(?:-([0-9]{1,5}))?", rule) if isinstance(rule, str) else None
        if m:
            lo = int(m.group(1)); hi = int(m.group(2) or lo)
            if 1 <= lo <= hi <= 65535:
                ports.update(range(lo, hi + 1))
    return ports


def explicit_grants(policy, src=EDGE_SRC):
    """{ip: ports} the policy already grants the edge ADDRESS on an explicit /32 destination (tag-based older grants are not counted: a port that is closed despite them is not covered)."""
    got = {}
    for g in policy.get("grants", []):
        if isinstance(g, dict) and src in (g.get("src") or []):
            for d in g.get("dst") or []:
                if isinstance(d, str) and d.endswith("/32"):
                    got.setdefault(d[:-3], set()).update(parse_ports(g.get("ip") or []))
    return got


def allowed_port(port):
    return port not in NEVER_PORTS and any(lo <= port <= hi for lo, hi in PORT_RANGES) and not any(lo <= port <= hi for lo, hi in MANAGEMENT_PORTS)


def parse_listening(ss_output, ip):
    """Ports reachable over the tailnet: bound to a wildcard or to the host's tailnet address (loopback-only is not)."""
    ports = set()
    for line in ss_output.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local = cols[3] if cols[0] == "LISTEN" and len(cols) >= 5 else cols[0]
        m = re.fullmatch(r"(\*|0\.0\.0\.0|\[::\]|::|" + re.escape(ip) + r"):(\d+)", local)
        if m:
            ports.add(int(m.group(2)))
    return ports


def listening_ports(ip, alias, run=subprocess.run):
    """The tailnet-reachable listening ports of one runtime, or None when they cannot be listed (no ssh, a timeout, an unreachable host,
    an empty answer): that destination is then `unverified` and nothing is granted blind, while the other destinations carry on."""
    try:
        r = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", alias, "ss -ltnH 2>/dev/null"], capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return parse_listening(r.stdout, ip)


def decide(closed, policy, listening_by_ip):
    """Classify every pair closed for MIN_STREAK runs. Returns a dict of lists plus `add`: {ip: sorted ports}."""
    granted = explicit_grants(policy)
    res = {"rejected": [], "already_granted": [], "stale": [], "unverified": [], "add": {}}
    for ip, port, streak in closed:
        if ip not in DESTINATIONS:
            res["rejected"].append((ip, port, "destination is not one of the pool runtimes")); continue
        if not allowed_port(port):
            res["rejected"].append((ip, port, "port is outside the pool ranges or on the never list")); continue
        if port in granted.get(ip, set()):
            res["already_granted"].append((ip, port, "closed although an explicit grant exists: not a missing grant")); continue
        listening = listening_by_ip.get(ip)
        if listening is None:
            res["unverified"].append((ip, port, "the sockets of %s could not be listed" % ip)); continue
        if port not in listening:
            res["stale"].append((ip, port, "nothing listens: a stale pool server, not a grant")); continue
        res["add"].setdefault(ip, set()).add(port)
    res["add"] = {ip: sorted(p) for ip, p in sorted(res["add"].items())}
    return res


# ---------------------------------------------------------------------------------------------------------------- policy edit + checks

def strict_parse(sync, text):
    """sync.parse_hujson, but a key that appears twice in one object is refused: Python keeps the last, Tailscale's own parser may keep the first or merge them,
    and a policy the two would read differently is a person's to fix, not something to build a grant on."""
    def hook(pairs):
        keys = [k for k, _ in pairs]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise Refusal("the policy has a duplicate key %s in one object: Python and Tailscale may read it differently" % dup[0])
        return dict(pairs)
    try:
        return json.loads(sync.standardize_hujson(text), object_pairs_hook=hook)
    except ValueError as e:
        raise CouldNotRun("the policy is not valid HuJSON: %s" % e)


def insert_blocks(policy_text, grants_block, tests_block, stamp):
    """Append the new blocks above the END markers. The markers must each exist exactly once (a person moved them: refuse)."""
    for marker in (GRANTS_END, TESTS_END):
        if policy_text.count(marker) != 1:
            raise CouldNotRun("the policy has %d copies of the marker %r: the job appends above it and needs exactly one" % (policy_text.count(marker), marker))

    def above(text, marker, block, label):
        i = text.index(marker)
        j = text.rfind("\n", 0, i) + 1                          # start of the marker's line
        indent = text[j:i]
        return text[:j] + indent + "// %s %s\n" % (stamp, label) + block + "\n" + text[j:]
    out = above(policy_text, GRANTS_END, grants_block, "auto: new standby edge grants (tier0-edge-grants job)")
    out = above(out, TESTS_END, tests_block, "auto: tests of the grants above")
    return out


def build_blocks(add, seg):
    grants, tests = seg.build({ip: set(p) for ip, p in add.items()}, EDGE_SRC)
    return seg.hujson(grants), seg.hujson(tests), grants, tests


def added_items(sync, live_items, new_items):
    """(removed, added) as multisets of canonical JSON, order ignored: what a policy change takes away and brings."""
    live_c = collections.Counter(sync._canon(x) for x in live_items)
    new_c = collections.Counter(sync._canon(x) for x in new_items)
    return live_c - new_c, new_c - live_c


def validate(sync, rec, guard, api, main_text, new_text, grants, tests):
    """Judge the change the way the reconciler will, against the LIVE policy. Raises Waiting when main is not applied yet, Refusal when this change is not exactly the job's own additions."""
    live_text, _etag = live_policy(sync, api)
    held = rec.classify(live_text, main_text, guard)
    if held.kind not in ("in_sync", "text_only"):
        raise Waiting("main and the live tailnet policy differ (%s): the reconciler has not applied what is merged, or it is blocked; the job adds nothing on top of that" % "; ".join(held.reasons or [held.kind])[:200])
    decision = rec.classify(live_text, new_text, guard)
    if decision.kind != "additive":
        raise Refusal("the reconciler would classify this change as %s (%s): it would not apply it by itself" % (decision.kind, "; ".join(decision.reasons)[:200]))
    live, new = strict_parse(sync, live_text), strict_parse(sync, new_text)
    removed_g, added_g = added_items(sync, live.get("grants", []), new.get("grants", []))
    removed_t, added_t = added_items(sync, live.get("tests", []), new.get("tests", []))
    own_g, own_t = collections.Counter(sync._canon(g) for g in grants), collections.Counter(sync._canon(t) for t in tests)
    if removed_g or removed_t or added_g != own_g or added_t != own_t:
        raise Refusal("the change against the LIVE policy holds more (or less) than the job's own %d grant(s) and %d test(s): %d grant(s) and %d test(s) would be added" % (
            len(grants), len(tests), sum(added_g.values()), sum(added_t.values())))
    errs = []
    for g in grants:
        errs += rec.grant_errors(g, {})
        errs += rec.coverage_errors(g, tests)
    if errs:
        raise Refusal("the reconciler's guard rejects the generated grants: " + "; ".join(errs)[:300])
    errs = sync.check_policy(new_text, guard) + sync.stored_form_errors(new_text)
    if errs:
        raise Refusal("policy check failed: " + "; ".join(errs)[:300])
    ok, msg = api.validate(new_text)
    if not ok:
        raise Refusal("the live validation (Tailscale API + every policy test) did not pass: " + msg[:300])
    return decision


def live_policy(sync, api):
    try:
        return api.get_policy()
    except sync.SyncError as e:
        raise CouldNotRun("cannot read the live policy: %s" % e)


def installed_errors(repo, pairs):
    """pairs: {path in the clone of main: installed copy}. The code that runs must be the code that was reviewed into main."""
    errs = []
    for rel, installed in pairs.items():
        try:
            git_text = (Path(repo) / rel).read_text()
        except OSError:
            errs.append("cannot read %s from the clone of main" % rel)
            continue
        try:
            have = Path(installed).read_text()
        except OSError:
            errs.append("the installed copy of %s is missing" % rel)
            continue
        if norm(have) != norm(git_text):
            errs.append("the installed %s differs from main: review it, then run scripts/tier0-edge-grants-install.sh" % rel)
    return errs


# ---------------------------------------------------------------------------------------------------------------- PR flow

def sh(cmd, cwd=None, run=subprocess.run, timeout=300, check=True):
    r = run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("%s failed: %s" % (" ".join(cmd[:3]), (r.stderr or r.stdout)[-300:]))
    return r


def gh_preflight(slug, repo, run=subprocess.run):
    """Before any branch or PR exists: this gh can read CI (`pr checks --json`), the token may push to the repository, and so may git (a dry-run push creates nothing)."""
    r = sh(["gh", "pr", "checks", "--help"], run=run, check=False)
    if "--json" not in (r.stdout or "") + (r.stderr or ""):
        raise CouldNotRun("this gh cannot `pr checks --json`: the job could not read CI, so it opens nothing")
    r = sh(["gh", "api", "repos/%s" % slug, "--jq", ".permissions.push"], run=run, check=False)
    if r.returncode != 0 or r.stdout.strip() != "true":
        raise CouldNotRun("gh has no push access to %s: %s" % (slug, ((r.stderr or r.stdout).strip() or "no answer")[:120]))
    r = sh(["git", "push", "--dry-run", "-q", "origin", "HEAD:refs/heads/" + BRANCH_PREFIX + "preflight-never-created"], cwd=repo, run=run, check=False)
    if r.returncode != 0:
        raise CouldNotRun("git cannot push to the repository: %s" % ((r.stderr or r.stdout).strip()[-160:] or "no answer"))


def open_auto_prs(repo_slug, run=subprocess.run):
    try:
        r = sh(["gh", "pr", "list", "--repo", repo_slug, "--state", "open", "--limit", "200", "--json", "number,headRefName,createdAt"], run=run)
        prs = json.loads(r.stdout or "[]")
    except (RuntimeError, ValueError) as e:
        raise CouldNotRun("cannot list the open pull requests: %s" % e)
    return [p for p in prs if isinstance(p, dict) and str(p.get("headRefName", "")).startswith(BRANCH_PREFIX)]


def parse_time(text):
    try:
        return int(datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())
    except (TypeError, ValueError):
        return None


def close_pr(repo_slug, number, why, run=subprocess.run):
    sh(["gh", "pr", "close", str(number), "--repo", repo_slug, "--delete-branch", "--comment", "tier0-edge-grants: %s" % why], run=run, check=False)


def wait_ci(repo_slug, number, run=subprocess.run, sleep=time.sleep, clock=time.time, limit=CI_WAIT_SECONDS, required=REQUIRED_CHECKS):
    """True only when every required context has reported and passed (an unrelated check that is fast, or a skipped one, is not CI); False when any check failed or was cancelled;
    None when the required ones did not all report green in time."""
    deadline = clock() + limit
    while clock() < deadline:
        r = sh(["gh", "pr", "checks", str(number), "--repo", repo_slug, "--json", "name,bucket"], run=run, check=False)
        try:
            checks = json.loads(r.stdout or "[]")
        except ValueError:
            checks = []
        buckets = collections.defaultdict(set)
        for c in checks if isinstance(checks, list) else []:
            if isinstance(c, dict):
                buckets[c.get("name")].add(c.get("bucket"))
        if any(b in ("fail", "cancel") for bs in buckets.values() for b in bs):
            return False
        if all(buckets.get(name) == {"pass"} for name in required):
            return True
        sleep(20)
    return None


def publish(repo, repo_slug, branch, new_text, summary, body, run=subprocess.run, sleep=time.sleep, clock=time.time, still_allowed=lambda: None, merge=True):
    """Branch, commit the policy file (and nothing else), push, PR, wait for CI, merge. Whatever goes wrong once a branch or PR exists, the PR is closed and the branch deleted, then the error goes on."""
    number = None
    pushed = False
    try:
        sh(["git", "checkout", "-q", "-b", branch], cwd=repo, run=run)
        (Path(repo) / "config" / "tailscale" / "policy.hujson").write_text(new_text)
        sh(["git", "add", "config/tailscale/policy.hujson"], cwd=repo, run=run)
        staged = sh(["git", "diff", "--cached", "--name-only"], cwd=repo, run=run).stdout.split()
        if staged != ["config/tailscale/policy.hujson"]:
            raise RuntimeError("refusing to commit: staged files are %s, expected only the policy" % staged[:5])
        sh(["git", "-c", "user.name=tier0-edge-grants", "-c", "user.email=tier0-edge-grants@ct108", "commit", "-q", "-m", summary, "-m", body + "\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], cwd=repo, run=run)
        sh(["git", "push", "-q", "-u", "origin", branch], cwd=repo, run=run)
        pushed = True
        r = sh(["gh", "pr", "create", "--repo", repo_slug, "--base", "main", "--head", branch, "--title", summary, "--body", body + "\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"], run=run)
        number = int(r.stdout.strip().rsplit("/", 1)[-1])
        verdict = wait_ci(repo_slug, number, run=run, sleep=sleep, clock=clock)
        if verdict is not True:
            raise RuntimeError("CI %s on PR #%d" % ("failed" if verdict is False else "gave no required result in time", number))
        still_allowed()
        if not merge:
            close_pr(repo_slug, number, "rehearsal: both CI contexts passed; closed on purpose, nothing was merged.", run)
            return number
        sh(["gh", "pr", "merge", str(number), "--repo", repo_slug, "--squash", "--delete-branch"], run=run)
        return number
    except BaseException as e:                                   # includes the SIGTERM of a systemd timeout (turned into KeyboardInterrupt by main)
        why = "%s: %s" % (type(e).__name__, str(e)[:160])
        if number is not None:
            close_pr(repo_slug, number, "the PR flow stopped (%s); closed, nothing was merged." % why, run)
        elif pushed:
            sh(["git", "push", "-q", "origin", "--delete", branch], cwd=repo, run=run, check=False)
        raise


# ---------------------------------------------------------------------------------------------------------------- state + metrics

STATE_COUNTERS = ("prs_total", "attempts_total", "failures", "attempts_today")
STATE_TIMES = ("last_pr_ts", "last_attempt_ts", "last_failure_ts")


def load_state(path, now=None):
    """The state file, validated: anything that is not what the job wrote counts as absent, and a time in the future (a clock that was wrong once) does not hold the job back."""
    now = int(time.time()) if now is None else now
    try:
        st = json.load(open(path))
    except (OSError, ValueError):
        st = {}
    if not isinstance(st, dict):
        st = {}
    clean = {}
    for k in STATE_COUNTERS:
        v = st.get(k, 0)
        clean[k] = v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10 ** 9 else 0
    for k in STATE_TIMES:
        v = st.get(k, 0)
        clean[k] = v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= now + 300 else 0
    clean["day"] = st["day"] if isinstance(st.get("day"), str) else ""
    clean["last_pr"] = st["last_pr"] if isinstance(st.get("last_pr"), int) and not isinstance(st.get("last_pr"), bool) else 0
    return clean


def save_state(path, st):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, path)


def write_metrics(textfile, values):
    if not textfile:
        return
    lines = []
    for k, v in values.items():
        lines.append("tier0_edge_grants_%s %s" % (k, v))
    tmp = textfile + ".tmp"
    open(tmp, "w").write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, textfile)


def previous_metrics(textfile):
    out = {}
    try:
        for l in open(textfile):
            m = re.match(r"tier0_edge_grants_(\w+) (\S+)", l)
            if m:
                out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def wait_between_attempts(failures):
    """Two hours between attempts; after a failed one the wait triples per consecutive failure, up to a day."""
    return MIN_SECONDS_BETWEEN_ATTEMPTS if not failures else min(MAX_BACKOFF, MIN_SECONDS_BETWEEN_ATTEMPTS * 3 ** failures)


# ---------------------------------------------------------------------------------------------------------------- main

def run_job(a, run=subprocess.run, sleep=time.sleep, clock=time.time, listing=listening_ports, api_login=None):
    now = int(clock())
    repo = a.repo
    dry, rehearse = bool(a.dry_run), bool(getattr(a, "rehearse", False))
    state_file = os.path.join(a.state, "state.json")
    st = load_state(state_file, now)
    metrics = {"last_run_timestamp_seconds": now, "ok": 1, "candidates": 0, "closed_pairs": 0, "rejected_pairs": 0, "stale_pairs": 0, "unverified_pairs": 0,
               "already_granted_pairs": 0, "capped": 0, "pr_open": 0, "waiting_reconciler": 0, "installed_matches_git": 1, "prs_total": st["prs_total"],
               "attempts_total": st["attempts_total"], "consecutive_failures": st["failures"], "last_pr_timestamp_seconds": st["last_pr_ts"]}
    prev = previous_metrics(a.textfile) if a.textfile else {}
    if "last_success_timestamp_seconds" in prev:
        metrics["last_success_timestamp_seconds"] = prev["last_success_timestamp_seconds"]
    report = {"status": "?", "add": {}}
    reconciler_pause = []                                         # filled once the tools are loaded

    def finish(status, code, ok):
        report["status"] = status
        metrics["ok"] = 1 if ok else 0
        metrics["consecutive_failures"] = st["failures"]
        if ok:
            metrics["last_success_timestamp_seconds"] = now
        if not dry and not rehearse:
            write_metrics(a.textfile, metrics)
        print("RESULT_JSON " + json.dumps(report))
        return code

    def job_paused():
        return os.path.exists(os.path.join(a.state, "PAUSE"))

    def any_paused():
        return job_paused() or any(os.path.exists(p) for p in reconciler_pause)

    def note_failure():
        if dry or rehearse:
            return
        st["failures"] += 1
        st["last_failure_ts"] = now
        save_state(state_file, st)
        metrics["consecutive_failures"] = st["failures"]

    try:
        if job_paused() and not rehearse:
            return finish("paused", 0, True)
        # the code that runs is the installed copy; it must be what was reviewed into main
        lib = Path(a.lib)
        errs = installed_errors(repo, {"scripts/tailscale_policy_sync.py": lib / "tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py": lib / "tailscale_policy_reconcile.py",
                                       "config/tailscale/lockout-guard.json": lib / "lockout-guard.json", "scripts/standby_edge_grants.py": HERE / "standby_edge_grants.py",
                                       "scripts/standby_edge_grants_job.py": Path(__file__).resolve()})
        if errs:
            metrics["installed_matches_git"] = 0
            raise CouldNotRun("; ".join(errs)[:400])
        try:
            sync = load_module("tailscale_policy_sync", lib / "tailscale_policy_sync.py")
            rec = load_module("tailscale_policy_reconcile", lib / "tailscale_policy_reconcile.py")
            seg = load_module("standby_edge_grants", HERE / "standby_edge_grants.py")
            guard = sync.load_guard(lib / "lockout-guard.json")
        except (OSError, SyntaxError, ImportError, AttributeError) as e:
            raise CouldNotRun("cannot load the installed tools: %s" % str(e)[:160])
        reconciler_pause.append(str(Path(getattr(a, "reconciler_state", None) or sync.DEFAULT_STATE_DIR) / "reconcile" / "PAUSE"))
        if not rehearse and any(os.path.exists(p) for p in reconciler_pause):
            metrics["waiting_reconciler"] = 1
            return finish("waiting: the tailnet policy reconciler is paused, so nothing merged would be applied", 0, True)
        main_text = (Path(repo) / "config" / "tailscale" / "policy.hujson").read_text()
        if not dry:
            gh_preflight(a.slug, repo, run)
        open_prs = [] if dry else open_auto_prs(a.slug, run)                       # a dry run never talks to GitHub
        metrics["pr_open"] = 1 if open_prs else 0
        if open_prs:
            report["open_pr"] = open_prs[0]["number"]
            stale = [p for p in open_prs if parse_time(p.get("createdAt")) is None or now - parse_time(p["createdAt"]) > STALE_PR_SECONDS]
            if stale:                                                                # a run that died: its PR must not hold the job back for ever
                for p in stale:
                    close_pr(a.slug, p["number"], "this automatic PR was open for more than %d hours (a run that did not finish); closed, nothing was merged." % (STALE_PR_SECONDS // 3600), run)
                report["closed_stale"] = [p["number"] for p in stale]
                metrics["pr_open"] = 1 if len(stale) < len(open_prs) else 0
                if not rehearse:
                    note_failure()
                return finish("closed %d stale automatic PR(s): the previous run did not finish" % len(stale), 5, False)
            return finish("a previous auto PR is still open", 0, True)
        closed = read_json(a.inject) if a.inject else read_closed(a.prom, a.proxy, now, run)
        closed = sorted({(c[0], int(c[1]), int(c[2]) if len(c) > 2 else MIN_STREAK) for c in closed})
        metrics["closed_pairs"] = len(closed)
        policy = strict_parse(sync, main_text)
        by_ip = {}
        for ip, port, _ in closed:
            if ip in DESTINATIONS and allowed_port(port):
                by_ip[ip] = True
        listen = {ip: listing(ip, DESTINATIONS[ip], run) for ip in by_ip}
        res = decide(closed, policy, listen)
        metrics.update(candidates=sum(len(p) for p in res["add"].values()), rejected_pairs=len(res["rejected"]), stale_pairs=len(res["stale"]),
                       unverified_pairs=len(res["unverified"]), already_granted_pairs=len(res["already_granted"]))
        report.update(add=res["add"], rejected=res["rejected"][:20], stale=res["stale"][:20], unverified=res["unverified"][:20], already_granted=res["already_granted"][:20])
        n = metrics["candidates"]
        if n == 0:
            return finish("nothing to grant", 0, True)
        if n > MAX_NEW_PORTS:
            metrics["capped"] = 1
            raise Refusal("%d new ports in one run (the limit is %d): an incident or a misconfiguration, a person decides" % (n, MAX_NEW_PORTS))
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        if st["day"] != today:
            st["day"], st["attempts_today"] = today, 0
        if not rehearse and (st["attempts_today"] >= MAX_ATTEMPTS_PER_DAY or now - st["last_attempt_ts"] < wait_between_attempts(st["failures"])):
            if st["failures"]:
                return finish("waiting: backing off after %d failed attempt(s) (the wait triples each time, up to a day); ok stays 0 until an attempt succeeds" % st["failures"], 0, False)
            return finish("waiting: the per-day or minimum-spacing limit for automatic PRs", 0, True)
        stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now))
        grants_block, tests_block, grants, tests = build_blocks(res["add"], seg)
        # In the form Tailscale stores it, whatever seg.hujson printed: CI refuses any other form (a text-only
        # difference after every apply), and so does validate() below.
        try:
            new_text = sync.stored_form(insert_blocks(main_text, grants_block, tests_block, stamp))
        except sync.SyncError as e:
            raise CouldNotRun("the policy is not valid HuJSON: %s" % e)
        strict_parse(sync, new_text)
        try:
            api = (api_login or sync.TailscaleAPI.login)()
        except sync.SyncError as e:
            raise CouldNotRun("cannot log in to Tailscale: %s" % e)
        validate(sync, rec, guard, api, main_text, new_text, grants, tests)
        ports = ", ".join("%s: %s" % (ip, ",".join(map(str, p))) for ip, p in res["add"].items())
        summary = "tailscale: the standby edge may reach %d more pool backend port(s) (automatic, tier0-edge-grants)" % n
        body = ("Written by the tier0-edge-grants job on CT108. The hourly edge-compat check TCP-tests every tailnet backend of the standby pools from the edge VM; these pairs have been closed for at least %d "
                "runs in a row, are listening on their hosts, are on the pool runtimes and in the pool port ranges, and are not granted yet: %s.\n\nAdditions only (one grant per host, /32, exact ports, a policy test "
                "per port). Verified before this PR, against the LIVE policy: main equals it, the reconciler's own classify() says `additive`, its guard and the offline check pass, Tailscale validates it "
                "with every policy test, and the difference is exactly these grants and tests. After merge the tailnet policy reconciler applies it (apply is on); the next edge-compat runs show the ports "
                "open. Kill switches: `touch %s/PAUSE` on CT108 (this job), `touch <reconciler state>/reconcile/PAUSE` (the reconciler)."
                % (MIN_STREAK, ports, a.state))
        if dry:
            report["would_open_pr"] = summary
            return finish("dry run: would open a PR", 0, True)
        branch = BRANCH_PREFIX + ("rehearsal-" if rehearse else "") + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        if rehearse:
            summary = "REHEARSAL, closed unmerged: " + summary
        else:                                                                        # the attempt is on record BEFORE anything is created: a crash, a kill or a red CI can never repeat it hourly
            st.update(day=today, attempts_today=st["attempts_today"] + 1, last_attempt_ts=now, attempts_total=st["attempts_total"] + 1)
            save_state(state_file, st)
            metrics["attempts_total"] = st["attempts_total"]

        def still_allowed():                                                         # looked at again just before the merge: a kill switch that appeared during the CI wait wins
            if not rehearse and any_paused():
                raise Paused()
        try:
            number = publish(repo, a.slug, branch, new_text, summary, body, run, sleep, clock, still_allowed=still_allowed, merge=not rehearse)
        except Paused:
            raise
        except KeyboardInterrupt:                                                     # stopped from outside (the builder's nightly backup halts it at 01:30 UTC, a reboot, systemctl stop): the PR was closed, and that is not the PR flow's fault
            report["interrupted"] = True                                              # the attempt stays on record (2 a day, 2 h apart), but no failure: no growing wait, the next run after the boot may go on
            return finish("PR flow interrupted from outside: its PR was closed, nothing was merged", 5, False)
        except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as e:
            report["pr_flow"] = (str(e) or type(e).__name__)[:300]
            note_failure()
            return finish("PR flow failed", 5, False)
        report["pr"] = number
        if rehearse:
            return finish("rehearsal: PR #%d passed CI and was closed unmerged" % number, 0, True)
        st.update(prs_total=st["prs_total"] + 1, last_pr_ts=now, last_pr=number, failures=0)
        save_state(state_file, st)
        metrics.update(prs_total=st["prs_total"], last_pr_timestamp_seconds=now)
        return finish("merged PR #%d" % number, 0, True)
    except Refusal as e:
        report["refused"] = str(e)
        return finish("refused", 4, False)
    except CouldNotRun as e:
        report["could_not_run"] = str(e)
        return finish("could not run", 3, False)
    except Waiting as e:
        report["waiting"] = str(e)
        metrics["waiting_reconciler"] = 1
        return finish("waiting: " + str(e), 0, True)
    except Paused:
        report["paused_while_open"] = True
        return finish("paused while the PR was open: closed, nothing was merged", 0, True)
    except KeyboardInterrupt:
        report["interrupted"] = True
        return finish("interrupted", 5, False)
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as e:
        report["could_not_run"] = (str(e) or type(e).__name__)[:300]
        return finish("could not run", 3, False)


def terminate(signum, frame):
    """systemd's timeout (SIGTERM): unwind instead of dying, so an open PR is closed instead of left behind."""
    raise KeyboardInterrupt("terminated by signal %d" % signum)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True, help="a (sparse) clone of the infrastructure repo (main): the policy and the git copies of the installed files")
    ap.add_argument("--slug", default="baditaflorin/platform_server")
    ap.add_argument("--state", required=True)
    ap.add_argument("--lib", default=DEFAULT_LIB, help="where the reconciler's tools are installed (tailscale_policy_sync.py, tailscale_policy_reconcile.py, lockout-guard.json)")
    ap.add_argument("--reconciler-state", help="the reconciler's state directory (default: the sync tool's), for its PAUSE file")
    ap.add_argument("--textfile")
    ap.add_argument("--prom", default="http://100.64.0.4:9090")
    ap.add_argument("--proxy", default="127.0.0.1:1055")
    ap.add_argument("--inject", help="JSON list of [ip, port, streak] instead of Prometheus (drills, tests)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--rehearse", action="store_true", help="the whole PR flow for real, but the PR is closed instead of merged; no state, no metrics")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, terminate)
    return run_job(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
