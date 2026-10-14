#!/usr/bin/env python3
"""Unattended reconciler for the SaaS tailnet policy (config/tailscale/policy.hujson).

Runs on CT108 from a systemd timer, next to the vault credential, and brings the live tailnet to the merged policy in
git ONLY when the change is small, additive and provable. Everything else is left for a human `plan`/`apply`
(scripts/tailscale_policy_sync.py) and alerted. CI never holds the credential; this is a pull reconciler.

One run
-------
1. Fetch the policy at origin/main (a squash-merged, reviewed change is the approval).
2. Refuse to act if the INSTALLED reconciler, sync tool or lockout guard differ from git: a PR must not be able to
   weaken the rules that judge it. Update the installed copy after review (scripts/tailscale-policy-reconcile-install.sh).
3. GET the live policy and classify the difference:
     in_sync    identical.
     text_only  same rules, comments or ordering differ.
     additive   the ONLY changes are new `grants` and new `tests`, every new grant passes the guard below and is
                proven by a new policy test.
     blocked    anything else: a removal, a changed section (groups, tagOwners, ssh, autoApprovers, nodeAttrs...),
                a failed offline check, a grant outside the guard.
4. For additive / text_only: require the CI status of that commit to be green, then validate with Tailscale (which
   also runs every policy `tests`), save a rollback copy, POST with `If-Match: <etag>`, and re-read to confirm.

Report-only by default: without --apply (or with a PAUSE file in the state directory) it decides and reports but
never applies. Bounded: one apply per run, a daily cap, and a circuit that stops retrying a commit that failed twice.

Guard for an auto-applied grant (anything else is a human decision)
-------------------------------------------------------------------
* only the keys src, dst and ip;
* src and dst are each at most MAX_ENDPOINTS entries, every one a single IPv4 host (/32) or a tag that exists in
  tagOwners: no users, groups, autogroups, wildcards, hosts or CIDR ranges;
* ip entries are explicit `tcp:N` / `udp:N` / `tcp:A-B` (a range spans at most MAX_PORT_SPAN ports) and none of
  them touch a management port (SSH, telnet, SMB, RDP, VNC, WinRM, hypervisor APIs);
* every (src, dst, port) of the grant is accepted by a test ADDED in the same change, so the policy API itself
  re-proves it at apply time and any later edit that breaks it is rejected.

State, metrics, alerts
----------------------
`<state-dir>/reconcile/state.json` and `events.jsonl` (audit); a node-exporter textfile
`tailscale_policy_reconcile.prom` (dead-man's switch `..._last_run_timestamp_seconds`); one ntfy notice per state
change, never one per run and never a secret. Exit codes: 0 ok / waiting, 1 an apply failed, 2 blocked (needs a
human; the alert has gone out), 3 could not look.

Only python3 stdlib is used; credentials come from tailscale_policy_sync (vault secret on CT108) and are never printed.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tailscale_policy_sync as tps  # noqa: E402

POLICY_PATH = "config/tailscale/policy.hujson"
GUARD_PATH = "config/tailscale/lockout-guard.json"
SYNC_PATH = "scripts/tailscale_policy_sync.py"
SELF_PATH = "scripts/tailscale_policy_reconcile.py"
CI_CONTEXT = "ci/woodpecker/push/woodpecker"

MAX_ADDED_GRANTS = 5
MAX_ENDPOINTS = 8
MAX_PORT_SPAN = 1000
MAX_APPLIES_PER_DAY = 3
CIRCUIT_FAILURES = 2
# Remote-administration surfaces: never opened unattended (inclusive ranges).
MANAGEMENT_PORTS = (
    (22, 23),  # ssh, telnet
    (135, 139),  # rpc, netbios
    (445, 445),  # smb
    (2222, 2222),  # alternate ssh
    (3389, 3389),  # rdp
    (5900, 5999),  # vnc
    (5985, 5986),  # winrm
    (8006, 8007),  # hypervisor and backup server apis
)
IP_RULE_RE = re.compile(r"^(tcp|udp):(\d{1,5})(?:-(\d{1,5}))?$")

DEFAULT_STATE_DIR = tps.DEFAULT_STATE_DIR
DEFAULT_TEXTFILE_DIR = Path("/var/lib/prometheus-node-exporter/textfile")


# ---------------------------------------------------------------------------------------------------------------
# Classification (pure)
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Decision:
    kind: str  # in_sync | text_only | additive | blocked
    reasons: list[str] = dataclasses.field(default_factory=list)
    added_grants: int = 0
    added_tests: int = 0


def _delta(live_items: list[Any], desired_items: list[Any]) -> tuple[list[str], list[str]]:
    """(removed, added) as canonical JSON strings, multiset semantics, order ignored."""
    live_c = collections.Counter(tps._canon(x) for x in live_items)
    want_c = collections.Counter(tps._canon(x) for x in desired_items)
    return list((live_c - want_c).elements()), list((want_c - live_c).elements())


def endpoint_errors(value: Any, owners: dict[str, Any]) -> list[str]:
    """One src/dst entry: a defined tag or a single IPv4 host. Everything broader needs a human."""
    if not isinstance(value, str):
        return ["not a string"]
    if value.startswith("tag:"):
        return [] if value in owners else [f"{value} is not defined in tagOwners"]
    try:
        net = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return ["not a literal address or a tag (users, groups, autogroups, wildcards and hosts need a human)"]
    if net.version != 4 or net.prefixlen != 32:
        return ["must be a single IPv4 host (/32) or a tag"]
    return []


def _ports(rule: str) -> tuple[str, int, int] | None:
    match = IP_RULE_RE.match(rule)
    if not match:
        return None
    lo = int(match.group(2))
    hi = int(match.group(3) or lo)
    if not (1 <= lo <= hi <= 65535):
        return None
    return match.group(1), lo, hi


def grant_errors(grant: Any, owners: dict[str, Any]) -> list[str]:
    """Why this ONE added grant may not be applied unattended (empty = acceptable)."""
    if not isinstance(grant, dict):
        return ["grant is not an object"]
    errors: list[str] = []
    extra = sorted(set(grant) - {"src", "dst", "ip"})
    if extra:
        errors.append(f"unsupported keys {extra} (only src, dst, ip)")
    for side in ("src", "dst"):
        items = grant.get(side)
        if not isinstance(items, list) or not items or not all(isinstance(x, str) for x in items):
            errors.append(f"{side} must be a non-empty list of strings")
            continue
        if len(items) > MAX_ENDPOINTS:
            errors.append(f"{side} lists {len(items)} entries (max {MAX_ENDPOINTS})")
        for item in items:
            errors.extend(f"{side} {item}: {err}" for err in endpoint_errors(item, owners))
    rules = grant.get("ip")
    if not isinstance(rules, list) or not rules:
        errors.append("ip must list explicit tcp/udp ports (no wildcard, no all-ports)")
        return errors
    for rule in rules:
        parsed = _ports(rule) if isinstance(rule, str) else None
        if parsed is None:
            errors.append(f"ip {rule!r}: only explicit tcp:N, udp:N or tcp:A-B are allowed")
            continue
        _, lo, hi = parsed
        if hi - lo + 1 > MAX_PORT_SPAN:
            errors.append(f"ip {rule}: spans {hi - lo + 1} ports (max {MAX_PORT_SPAN})")
        for m_lo, m_hi in MANAGEMENT_PORTS:
            if lo <= m_hi and hi >= m_lo:
                errors.append(f"ip {rule}: touches management ports {m_lo}-{m_hi}")
                break
    return errors


def _bare_host(value: str) -> str:
    return value[:-3] if value.endswith("/32") else value


def coverage_errors(grant: dict[str, Any], added_tests: list[dict[str, Any]]) -> list[str]:
    """Every (src, dst, port) of the grant must be accepted by a test added in the same change."""
    errors: list[str] = []
    for src in grant.get("src", []):
        for dst in grant.get("dst", []):
            for rule in grant.get("ip", []):
                parsed = _ports(rule)
                if parsed is None:
                    continue
                proto, lo, hi = parsed
                for port in sorted({lo, hi}):
                    want = f"{_bare_host(dst)}:{port}"
                    covered = any(
                        _bare_host(str(test.get("src", ""))) == _bare_host(src)
                        and test.get("proto", proto) == proto
                        and want in (test.get("accept") or [])
                        for test in added_tests
                    )
                    if not covered:
                        errors.append(f"no added policy test accepts {_bare_host(src)} -> {want} ({proto})")
    return errors


def classify(live_text: str, desired_text: str, guard: dict[str, Any]) -> Decision:
    try:
        live = tps.parse_hujson(live_text)
        desired = tps.parse_hujson(desired_text)
    except tps.SyncError as exc:
        return Decision("blocked", [str(exc)])
    if not isinstance(live, dict) or not isinstance(desired, dict):
        return Decision("blocked", ["policy root must be an object"])

    reasons = [f"offline check: {err}" for err in tps.check_policy(desired_text, guard)]
    owners = desired.get("tagOwners") if isinstance(desired.get("tagOwners"), dict) else {}
    added: dict[str, list[Any]] = {"grants": [], "tests": []}
    for key in sorted(set(live) | set(desired)):
        if key in ("grants", "tests"):
            lv, dv = live.get(key, []), desired.get(key, [])
            if not isinstance(lv, list) or not isinstance(dv, list):
                reasons.append(f"{key} is not a list")
                continue
            removed, new = _delta(lv, dv)
            if removed:
                reasons.append(f"removes {len(removed)} entries from {key}")
            added[key] = [json.loads(item) for item in new]
        elif tps._canon(live.get(key)) != tps._canon(desired.get(key)) or (key in live) != (key in desired):
            reasons.append(f"section {key} differs")

    if len(added["grants"]) > MAX_ADDED_GRANTS:
        reasons.append(f"adds {len(added['grants'])} grants (max {MAX_ADDED_GRANTS} per change)")
    added_tests = [t for t in added["tests"] if isinstance(t, dict)]
    for grant in added["grants"]:
        errs = grant_errors(grant, owners)
        if not errs:
            errs = coverage_errors(grant, added_tests)
        reasons.extend(f"added grant {tps._canon(grant)[:120]}: {err}" for err in errs)

    if reasons:
        return Decision("blocked", reasons, len(added["grants"]), len(added["tests"]))
    if not added["grants"] and not added["tests"]:
        same_text = tps.normalise_text(live_text) == tps.normalise_text(desired_text)
        return Decision("in_sync" if same_text else "text_only")
    return Decision("additive", [], len(added["grants"]), len(added["tests"]))


# ---------------------------------------------------------------------------------------------------------------
# Sources: git and CI status
# ---------------------------------------------------------------------------------------------------------------


def repo_slug(url: str) -> str:
    match = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", url.strip())
    if not match:
        raise tps.SyncError("repo URL is not a github.com URL")
    return match.group(1)


class GitSource:
    """origin/main of the policy repository, read through git (a credential helper on CT108), CI state through gh."""

    def __init__(self, repo_dir: Path, repo_url: str, branch: str = "main") -> None:
        self.repo_dir, self.repo_url, self.branch = repo_dir, repo_url, branch
        self._env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        try:
            res = subprocess.run(  # noqa: S603
                ["git", *args], cwd=cwd or self.repo_dir, capture_output=True, text=True, timeout=180, env=self._env
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise tps.SyncError(f"git {args[0]} failed ({type(exc).__name__})") from exc
        if res.returncode != 0:
            raise tps.SyncError(f"git {args[0]} failed: {res.stderr.strip()[:200]}")
        return res.stdout

    def head(self) -> str:
        if not (self.repo_dir / ".git").exists():
            self.repo_dir.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", "--quiet", "--filter=blob:none", "--no-checkout", self.repo_url, str(self.repo_dir), cwd=self.repo_dir.parent)
        self._git("fetch", "--quiet", "--depth", "50", "origin", self.branch)
        return self._git("rev-parse", f"origin/{self.branch}").strip()

    def file(self, path: str, sha: str) -> str:
        return self._git("show", f"{sha}:{path}")

    def ci_status(self, sha: str) -> str:
        """success | pending | failure | unknown for the required CI context on this exact commit."""
        try:
            res = subprocess.run(  # noqa: S603
                ["gh", "api", f"repos/{repo_slug(self.repo_url)}/commits/{sha}/status"],
                capture_output=True, text=True, timeout=60, env=self._env,
            )
            if res.returncode != 0:
                return "unknown"
            statuses = json.loads(res.stdout).get("statuses", [])
        except (OSError, subprocess.TimeoutExpired, ValueError, tps.SyncError):
            return "unknown"
        for status in statuses:
            if status.get("context") == CI_CONTEXT:
                state = status.get("state")
                return {"success": "success", "pending": "pending", "failure": "failure", "error": "failure"}.get(state, "unknown")
        return "unknown"


# ---------------------------------------------------------------------------------------------------------------
# State, metrics, alerts
# ---------------------------------------------------------------------------------------------------------------


def _state_file(state_dir: Path) -> Path:
    return state_dir / "reconcile" / "state.json"


def load_state(state_dir: Path) -> dict[str, Any]:
    try:
        state = json.loads(_state_file(state_dir).read_text())
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def save_state(state_dir: Path, state: dict[str, Any]) -> None:
    tps._write_private(_state_file(state_dir), json.dumps(state, indent=2, sort_keys=True))


def log_event(state_dir: Path, event: dict[str, Any], now: float) -> None:
    path = state_dir / "reconcile" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": int(now), **event}, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def write_metrics(textfile_dir: Path | None, values: dict[str, float]) -> None:
    if textfile_dir is None:
        return
    help_text = {
        "last_run_timestamp_seconds": "Unix time of the last completed reconcile run (dead-man switch).",
        "last_success_timestamp_seconds": "Unix time of the last run that left live == git or applied a change.",
        "in_sync": "1 if the live tailnet policy equals the merged policy in git.",
        "blocked": "1 if a merged change needs a human (not auto-appliable).",
        "pending_apply": "1 if an additive change is waiting (CI, report-only mode or a cap).",
        "applied_total": "Policy applies performed by the reconciler.",
        "look_ok": "1 if the last run could read git and the live policy (0 = could not look).",
        "apply_enabled": "1 if this run was allowed to apply.",
    }
    lines: list[str] = []
    for name, value in values.items():
        metric = f"tailscale_policy_reconcile_{name}"
        kind = "counter" if name.endswith("_total") else "gauge"
        lines += [f"# HELP {metric} {help_text.get(name, name)}", f"# TYPE {metric} {kind}", f"{metric} {value}"]
    textfile_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=textfile_dir, prefix=".tailscale_policy_reconcile.")
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)  # node_exporter runs as another user: a 0600 textfile is silently skipped
    os.replace(tmp, textfile_dir / "tailscale_policy_reconcile.prom")


def ntfy_notifier(url: str | None) -> Callable[[str, str], None]:
    """Best-effort notice: a dead channel never stops a run. The body never carries a secret or an address."""

    def notify(title: str, body: str) -> None:
        if not url:
            return
        try:
            req = urllib.request.Request(url, data=body.encode(), method="POST", headers={"Title": title})
            urllib.request.urlopen(req, timeout=10).read()  # noqa: S310
        except Exception:  # noqa: BLE001
            pass

    return notify


def _notice_once(state: dict[str, Any], key: str, notify: Callable[[str, str], None], title: str, body: str) -> None:
    if state.get("notified") != key:
        notify(title, body)
        state["notified"] = key


# ---------------------------------------------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------------------------------------------


def _integrity_errors(source: Any, sha: str, local: dict[str, Path]) -> list[str]:
    """The installed reconciler, sync tool and guard must equal the ones in git at this commit."""
    errors = []
    for repo_path, local_path in local.items():
        try:
            git_text = source.file(repo_path, sha)
        except tps.SyncError as exc:
            errors.append(f"cannot read {repo_path} from git: {exc}")
            continue
        try:
            have = tps.sha256(tps.normalise_text(local_path.read_text()))
        except OSError:
            errors.append(f"installed copy of {repo_path} is missing")
            continue
        if have != tps.sha256(tps.normalise_text(git_text)):
            errors.append(f"installed {repo_path} differs from git: review it, then reinstall")
    return errors


def _applies_today(state: dict[str, Any], now: float) -> int:
    return sum(1 for ts in state.get("applied", []) if now - ts < 86400)


def run_once(
    *,
    api_login: Callable[[], Any],
    source: Any,
    guard: dict[str, Any],
    local_files: dict[str, Path],
    state_dir: Path,
    textfile_dir: Path | None,
    apply_enabled: bool,
    notify: Callable[[str, str], None],
    now: Callable[[], float] = time.time,
) -> int:
    state = load_state(state_dir)
    paused = (state_dir / "reconcile" / "PAUSE").exists()
    can_apply = apply_enabled and not paused
    metrics: dict[str, float] = {"apply_enabled": 1 if can_apply else 0, "look_ok": 1}

    def finish(code: int, **extra: float) -> int:
        metrics.update(extra)
        metrics["last_run_timestamp_seconds"] = int(now())
        metrics["applied_total"] = state.get("applied_count", 0)
        if code == 0 and metrics.get("in_sync") == 1:
            state["last_success"] = int(now())
        if state.get("last_success"):
            metrics["last_success_timestamp_seconds"] = state["last_success"]
        save_state(state_dir, state)
        write_metrics(textfile_dir, metrics)
        return code

    try:
        sha = source.head()
        desired_text = source.file(POLICY_PATH, sha)
        problems = _integrity_errors(source, sha, local_files)
        api = api_login()
        live_text, etag = api.get_policy()
    except tps.SyncError as exc:
        log_event(state_dir, {"event": "could_not_look", "error": str(exc)[:200]}, now())
        print(f"reconcile: could not look: {exc}", file=sys.stderr)
        return finish(3, look_ok=0)

    decision = classify(live_text, desired_text, guard)
    if problems:
        decision = Decision("blocked", [*problems, *decision.reasons])
    state["last_sha"] = sha
    print(f"reconcile: commit {sha[:12]}, live etag {etag}, decision {decision.kind}, apply {'on' if can_apply else 'off'}")

    if decision.kind == "in_sync":
        if state.get("notified"):
            notify("tailnet policy: back in sync", f"Live policy equals git at {sha[:12]}.")
            state["notified"] = ""
        state["failures"] = {}
        return finish(0, in_sync=1, blocked=0, pending_apply=0)

    if decision.kind == "blocked":
        key = "blocked:" + hashlib.sha256("\n".join(decision.reasons).encode()).hexdigest()[:12]
        for reason in decision.reasons:
            print(f"  BLOCKED: {reason}")
        log_event(state_dir, {"event": "blocked", "sha": sha, "reasons": decision.reasons[:20]}, now())
        _notice_once(
            state, key, notify, "tailnet policy: needs a human",
            f"Merged policy {sha[:12]} differs from live and cannot be applied unattended "
            f"({len(decision.reasons)} reason(s)). Run scripts/tailscale-policy-ct108.sh plan; details in the reconcile events log.",
        )
        return finish(2, in_sync=0, blocked=1, pending_apply=0)

    # additive or text_only
    ci = source.ci_status(sha)
    print(f"  CI status of the commit: {ci}")
    if ci != "success":
        if ci == "failure":
            log_event(state_dir, {"event": "ci_failed", "sha": sha}, now())
            _notice_once(state, f"ci:{sha}", notify, "tailnet policy: CI failed", f"CI failed on {sha[:12]}; nothing applied.")
        return finish(0 if ci != "failure" else 2, in_sync=0, blocked=1 if ci == "failure" else 0, pending_apply=0 if ci == "failure" else 1)

    fail = state.get("failures") or {}
    if fail.get("sha") == sha and fail.get("count", 0) >= CIRCUIT_FAILURES:
        _notice_once(state, f"circuit:{sha}", notify, "tailnet policy: reconcile stopped",
                     f"Applying {sha[:12]} failed {fail['count']} times; not retrying until main moves.")
        return finish(2, in_sync=0, blocked=1, pending_apply=1)

    if not can_apply:
        why = "PAUSE file present" if paused else "report-only mode"
        print(f"  would apply {decision.added_grants} grant(s) and {decision.added_tests} test(s): {why}")
        log_event(state_dir, {"event": "would_apply", "sha": sha, "why": why}, now())
        _notice_once(state, f"would:{sha}", notify, "tailnet policy: change waiting",
                     f"{sha[:12]} adds {decision.added_grants} grant(s); not applied ({why}).")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)

    if _applies_today(state, now()) >= MAX_APPLIES_PER_DAY:
        _notice_once(state, f"cap:{sha}", notify, "tailnet policy: daily cap", f"{MAX_APPLIES_PER_DAY} applies in 24h; {sha[:12]} waits.")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)

    ok, msg = api.validate(desired_text)
    if not ok:
        return _failed(state, state_dir, sha, f"validate failed: {msg[:200]}", notify, now, finish)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now()))
    rollback = state_dir / "rollback" / f"policy.{stamp}.{etag.strip(chr(34))[:12]}.hujson"
    tps._write_private(rollback, live_text)
    status, body = api.set_policy(desired_text, etag)
    if status == 412:
        print("  live policy changed while reconciling (ETag): retrying next run")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)
    if status != 200:
        return _failed(state, state_dir, sha, f"apply refused: HTTP {status}: {body[:200]}", notify, now, finish)

    try:
        after, new_etag = api.get_policy()
        left = tps.semantic_diff(tps.parse_hujson(after), tps.parse_hujson(desired_text))
    except tps.SyncError as exc:  # the apply itself succeeded; do not lose that fact
        new_etag, left = "?", [f"could not re-read the live policy: {exc}"]
    state.setdefault("applied", []).append(int(now()))
    state["applied"] = state["applied"][-20:]
    state["applied_count"] = state.get("applied_count", 0) + 1
    state["last_applied_sha"] = sha
    state["failures"] = {}
    log_event(state_dir, {"event": "applied", "sha": sha, "etag_before": etag, "etag_after": new_etag,
                          "grants": decision.added_grants, "tests": decision.added_tests, "rollback": str(rollback),
                          "post_apply_diff": left[:5]}, now())
    notify("tailnet policy: applied", f"Applied {sha[:12]} ({decision.added_grants} grant(s), {decision.added_tests} test(s)). Rollback copy saved.")
    state["notified"] = ""
    print(f"  applied; new etag {new_etag}; post-apply diff {'EMPTY' if not left else left}")
    return finish(0 if not left else 1, in_sync=1 if not left else 0, blocked=0, pending_apply=0)


def _failed(state, state_dir, sha, message, notify, now, finish) -> int:
    fail = state.get("failures") or {}
    count = fail.get("count", 0) + 1 if fail.get("sha") == sha else 1
    state["failures"] = {"sha": sha, "count": count}
    print(f"  FAILED: {message}", file=sys.stderr)
    log_event(state_dir, {"event": "apply_failed", "sha": sha, "message": message}, now())
    _notice_once(state, f"fail:{sha}:{count}", notify, "tailnet policy: apply failed", f"Applying {sha[:12]} failed (attempt {count}); live policy unchanged.")
    return finish(1, in_sync=0, blocked=0, pending_apply=1)


# ---------------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------------


def cmd_reconcile(args: argparse.Namespace) -> int:
    here = Path(__file__).resolve().parent
    guard_path = args.guard or (here / "lockout-guard.json")
    guard = tps.load_guard(guard_path)
    local = {SYNC_PATH: here / "tailscale_policy_sync.py", SELF_PATH: Path(__file__).resolve(), GUARD_PATH: guard_path}
    if not args.repo_url:
        raise tps.SyncError("--repo-url (or FLEET_TS_RECONCILE_REPO_URL) is required")
    source = GitSource(args.repo_dir, args.repo_url, args.branch)
    return run_once(
        api_login=tps.TailscaleAPI.login,
        source=source,
        guard=guard,
        local_files=local,
        state_dir=args.state_dir,
        textfile_dir=args.textfile_dir,
        apply_enabled=args.apply,
        notify=ntfy_notifier(os.environ.get("FLEET_TS_RECONCILE_NTFY_URL")),
    )


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state(args.state_dir)
    print(json.dumps(state, indent=2, sort_keys=True) if state else "no reconcile state yet")
    print(f"PAUSE: {'yes' if (args.state_dir / 'reconcile' / 'PAUSE').exists() else 'no'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("reconcile", help="decide, and apply only an additive, guarded, CI-green change")
    p.add_argument("--apply", action="store_true", help="allow applying (default: report only)")
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--textfile-dir", type=Path, default=DEFAULT_TEXTFILE_DIR)
    p.add_argument("--repo-dir", type=Path, default=DEFAULT_STATE_DIR / "reconcile" / "repo")
    p.add_argument("--repo-url", default=os.environ.get("FLEET_TS_RECONCILE_REPO_URL", ""))
    p.add_argument("--branch", default="main")
    p.add_argument("--guard", type=Path, default=None, help="installed lockout guard (default: next to this script)")
    p.set_defaults(func=cmd_reconcile)
    p = sub.add_parser("status", help="print the reconcile state")
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)
    try:
        return args.func(args)
    except tps.SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
