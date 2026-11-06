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
3. GET the live policy. An ETag other than the one this reconciler last saw or produced is a change it did not make
   (a hand apply): it is logged, counted (`..._out_of_band_changes_total`, alert FleetTailnetPolicyChangedOutsideReconciler)
   and announced. Then classify the difference:
     in_sync    identical, or live is exactly what Tailscale stores when git's text is posted (tps.stored_form).
     text_only  same rules, comments or ordering differ.
     additive   the ONLY changes are new `grants` and new `tests`, every new grant passes the guard below and is
                proven by a new policy test.
     blocked    anything else: a removal, a changed section (groups, tagOwners, ssh, autoApprovers, nodeAttrs...),
                a failed offline check, a grant outside the guard.
4. For additive / text_only: require the CI status of that commit to be green, then validate with Tailscale (which
   also runs every policy `tests`), save a rollback copy, POST with `If-Match: <etag>`, and re-read to confirm.

Report-only by default: without --apply (or with a PAUSE file in the state directory) it decides and reports but
never applies. Bounded: one apply per run, a daily cap on rule-changing (additive) applies, and a circuit that stops
retrying a commit that failed twice. A text-only apply changes no rule, so it is not capped; it is made at most once
per policy text, because one that leaves live in yet another form would otherwise repeat every run.

Guard for an auto-applied grant (anything else is a human decision)
-------------------------------------------------------------------
* only the keys src, dst and ip;
* src and dst are each at most MAX_ENDPOINTS entries, every one a single IPv4 host (/32) or a tag that exists in
  tagOwners: no users, groups, autogroups, wildcards, hosts or CIDR ranges;
* ip entries are explicit `tcp:N` / `udp:N` / `tcp:A-B` (a range spans at most MAX_PORT_SPAN ports) and none of
  them touch a management port (SSH, telnet, SMB, RDP, VNC, WinRM, hypervisor APIs);
* every (src, dst, port) of the grant is accepted by a test ADDED in the same change, so the policy API itself
  re-proves it at apply time and any later edit that breaks it is rejected.

An existing test may change in one way only: destinations move from its `deny` list to its `accept` list, each opened
(dst, port, protocol) by a grant added in the same change, and nothing else about the test changes. Such a test held
`deny` on live, the only rule change is the guarded new grants, and the policy API runs every test before the apply,
so the `accept` can only pass if a new grant opens it for that source. Only the moved destinations count as proof of a
new grant. Any other change to a test is a removal and needs a human.

State, metrics, alerts
----------------------
`<state-dir>/reconcile/state.json` and `events.jsonl` (audit); a node-exporter textfile
`tailscale_policy_reconcile.prom` (dead-man's switch `..._last_run_timestamp_seconds`); one ntfy notice per state
change, never one per run and never a secret. A run held back by the daily cap prints `daily cap: ...` with the time the next
slot frees and logs a `deferred_cap` event; a notice that could not be sent prints `notice failed (<error class>)` (no URL, no
error text); an audit line that could not be written after an apply prints `audit event not written (<error class>)` and does not cost
the apply its state save; a state.json field of the wrong type is dropped with a one-line `state.json field ... was reset` note
(never the value). Exit codes: 0 ok / waiting, 1 an apply failed, 2 blocked (needs a human; the alert has gone out), 3 could not look.

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


def _opened_by(dest: Any, proto: str, grants: list[Any]) -> bool:
    """`host:port` (a test destination) is opened for `proto` by one of these grants (dst and port only)."""
    if not isinstance(dest, str) or ":" not in dest:
        return False
    host, _, port = dest.rpartition(":")
    if not port.isdigit():
        return False
    for grant in grants:
        if not isinstance(grant, dict) or _bare_host(host) not in {_bare_host(d) for d in grant.get("dst", []) if isinstance(d, str)}:
            continue
        for rule in grant.get("ip", []):
            parsed = _ports(rule) if isinstance(rule, str) else None
            if parsed and parsed[0] == proto and parsed[1] <= int(port) <= parsed[2]:
                return True
    return False


def deny_to_accept(old: Any, new: Any, added_grants: list[Any]) -> list[str] | None:
    """The destinations `new` moved from `old`'s deny to its accept, when that is ALL that changed and each one is opened
    by a grant added in this change; otherwise None. The source is not compared: a node's tag is not known offline
    (#539 changed a tag test and the test of that tag's node by IP), and the policy API proves it before any apply."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    rest_old = {k: v for k, v in old.items() if k not in ("accept", "deny")}
    rest_new = {k: v for k, v in new.items() if k not in ("accept", "deny")}
    if tps._canon(rest_old) != tps._canon(rest_new):
        return None
    lists = [old.get("accept", []), old.get("deny", []), new.get("accept", []), new.get("deny", [])]
    if not all(isinstance(x, list) and all(isinstance(d, str) for d in x) for x in lists):
        return None
    old_accept, old_deny, new_accept, new_deny = (collections.Counter(x) for x in lists)
    moved = new_accept - old_accept
    if not moved or old_accept - new_accept or old_deny - new_deny != moved or new_deny - old_deny:
        return None  # nothing moved, an accept was lost, or deny lost or gained anything but the moved destinations
    proto = old.get("proto", "tcp")
    if not all(_opened_by(dest, proto, added_grants) for dest in moved):
        return None
    return sorted(moved.elements())


def _pair_test_changes(removed: list[Any], added_tests: list[Any], added_grants: list[Any]) -> tuple[list[Any], list[Any]]:
    """(removed tests that are not a deny-to-accept move, the added tests that may prove a new grant). A moved test
    proves only its moved destinations: its other accepts were there before and prove nothing new."""
    free = list(added_tests)
    unpaired, proofs = [], []
    for old in removed:
        for i, new in enumerate(free):
            moved = deny_to_accept(old, new, added_grants)
            if moved is not None:
                proofs.append({**free.pop(i), "accept": moved})
                break
        else:
            unpaired.append(old)
    return unpaired, proofs + free


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
    removed_tests: list[Any] = []
    for key in sorted(set(live) | set(desired)):
        if key in ("grants", "tests"):
            lv, dv = live.get(key, []), desired.get(key, [])
            if not isinstance(lv, list) or not isinstance(dv, list):
                reasons.append(f"{key} is not a list")
                continue
            removed, new = _delta(lv, dv)
            if key == "tests":
                removed_tests = [json.loads(item) for item in removed]
            elif removed:
                reasons.append(f"removes {len(removed)} entries from {key}")
            added[key] = [json.loads(item) for item in new]
        elif tps._canon(live.get(key)) != tps._canon(desired.get(key)) or (key in live) != (key in desired):
            reasons.append(f"section {key} differs")

    # A changed test is a removal plus an addition, except a deny-to-accept move for a new grant (see the module doc).
    unpaired, proofs = _pair_test_changes(removed_tests, added["tests"], added["grants"])
    if unpaired:
        reasons.append(f"removes {len(unpaired)} entries from tests")
    if len(added["grants"]) > MAX_ADDED_GRANTS:
        reasons.append(f"adds {len(added['grants'])} grants (max {MAX_ADDED_GRANTS} per change)")
    added_tests = [t for t in proofs if isinstance(t, dict)]
    for grant in added["grants"]:
        errs = grant_errors(grant, owners)
        if not errs:
            errs = coverage_errors(grant, added_tests)
        reasons.extend(f"added grant {tps._canon(grant)[:120]}: {err}" for err in errs)

    if reasons:
        return Decision("blocked", reasons, len(added["grants"]), len(added["tests"]))
    if not added["grants"] and not added["tests"]:
        if tps.normalise_text(live_text) == tps.normalise_text(desired_text):
            return Decision("in_sync")
        # Tailscale keeps a posted policy re-formatted (tps.stored_form). When live is exactly what posting git would
        # store, an apply changes nothing: that loop re-applied #526 and spent the daily cap on 2026-10-20.
        if tps.normalise_text(live_text) == tps.normalise_text(stored_or_none(desired_text) or ""):
            return Decision("in_sync", ["git's text is not in Tailscale's stored form; live is that form (tailscale_policy_sync.py fmt writes it)"])
        return Decision("text_only")
    return Decision("additive", [], len(added["grants"]), len(added["tests"]))


def stored_or_none(text: str) -> str | None:
    try:
        return tps.stored_form(text)
    except tps.SyncError:
        return None


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


def _is_count(value: Any) -> bool:
    # bounded: a literal too big for a float64 becomes a sample node_exporter's parser rejects, which blinds the dead-man alert
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**53


def _is_time(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) < 1e15


# The type each state field must have to be used as it is. The reconciler only ever writes these shapes; anything else comes from
# a hand edit or damage. A field of the wrong type used to crash a run, some of them AFTER the tailnet POST (applied_count, the
# out_of_band counters), which skipped the state save: the apply was never counted against the cap. A wrong-typed field is now
# dropped, as if it were missing, and the journal says which one (never its value). `applied` is not here: _window reads it fail
# closed (an unreadable history holds the cap), because dropping it would lift the cap.
_STATE_FIELDS: dict[str, Callable[[Any], bool]] = {
    "applied_count": _is_count,
    "failures": lambda v: isinstance(v, dict) and ("count" not in v or _is_count(v["count"])),
    "out_of_band": lambda v: isinstance(v, dict) and all(isinstance(k, str) and _is_count(c) for k, c in v.items()),
    "out_of_band_last": _is_time,
    "last_success": _is_time,
    "live_etag": lambda v: v is None or isinstance(v, str),
    "notified": lambda v: isinstance(v, str),
    "unconverged": lambda v: isinstance(v, str),
    "last_sha": lambda v: isinstance(v, str),
    "last_applied_sha": lambda v: isinstance(v, str),
}


def load_state(state_dir: Path) -> dict[str, Any]:
    try:
        state = json.loads(_state_file(state_dir).read_text())
    except (FileNotFoundError, ValueError):
        return {}
    if not isinstance(state, dict):
        return {}
    for name, usable in _STATE_FIELDS.items():
        if name in state and not usable(state[name]):
            _say(f"reconcile: state.json field {name} had the wrong type ({type(state.pop(name)).__name__}) and was reset", err=True)
    return state


def save_state(state_dir: Path, state: dict[str, Any]) -> None:
    tps._write_private(_state_file(state_dir), json.dumps(state, indent=2, sort_keys=True))


def log_event(state_dir: Path, event: dict[str, Any], now: float) -> None:
    path = state_dir / "reconcile" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": int(now), **event}, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def _say(message: str, *, err: bool = False) -> None:
    """A line for the journal that can never decide a run: a dead or closed stream is ignored (a run that has already changed the
    tailnet must still reach its state save)."""
    try:
        print(message, file=sys.stderr if err else None)
    except Exception:  # noqa: BLE001
        pass


def _log_best_effort(state_dir: Path, event: dict[str, Any], now: float) -> bool:
    """log_event for the lines that must not decide a run's fate: the one written after the tailnet was changed (an exception there
    skipped the state save, so the apply was never counted against the cap and the next run read the new ETag as a change from
    outside) and the deferral report. The failure is said on stderr, event name and error class only, and is itself best-effort."""
    try:
        log_event(state_dir, event, now)
        return True
    except Exception as exc:  # noqa: BLE001
        try:
            _say(f"reconcile: audit event not written ({type(exc).__name__}): {event.get('event')}", err=True)
        except Exception:  # noqa: BLE001
            pass
        return False


def write_metrics(textfile_dir: Path | None, values: dict[str, float]) -> None:
    """`values` keys are metric names after the prefix, optionally with labels (`name{via="unknown"}`)."""
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
        "git_stored_form": "1 if the policy text in git is exactly what Tailscale stores (hujson.Format), so live can equal it byte for byte.",
        "out_of_band_changes_total": "Live policy changes (ETag changes) the reconciler did not make; via=sync_tool is a recorded tailscale_policy_sync.py apply.",
        "last_out_of_band_timestamp_seconds": "Unix time the reconciler last found a live policy change it did not make (0 = never).",
    }
    lines: list[str] = []
    for name, value in values.items():
        family = name.split("{", 1)[0]
        metric = f"tailscale_policy_reconcile_{family}"
        kind = "counter" if family.endswith("_total") else "gauge"
        if f"# TYPE {metric} {kind}" not in lines:
            lines += [f"# HELP {metric} {help_text.get(family, family)}", f"# TYPE {metric} {kind}"]
        lines.append(f"tailscale_policy_reconcile_{name} {value}")
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
        except Exception as exc:  # noqa: BLE001
            # Never stops a run, but a channel that refuses or cannot be reached must not be invisible: the journal gets the title,
            # the error class and an integer HTTP status, never the URL (the topic is the secret) nor the error text (urllib puts the
            # URL in it). Reporting is itself best-effort: a dead stderr or an exception whose `code` cannot be read must not turn a
            # failed notice into an exception that skips the state save.
            try:
                status = getattr(exc, "code", None)
            except Exception:  # noqa: BLE001
                status = None
            http = f" HTTP {status}" if type(status) is int else ""
            _say(f"reconcile: notice failed ({type(exc).__name__}{http}): {title}", err=True)

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


def _window(state: dict[str, Any], now: float) -> list[float | None]:
    """The `applied` entries that count against the cap: the readable ones inside the rolling 24 h, as numbers, plus one None for each
    entry that cannot be read as a time (and MAX_APPLIES_PER_DAY of them when `applied` is not a list at all). Fail closed: an
    unreadable `applied` can hold the cap but not lift it, and cannot crash the run before the notice, the metrics and the state save.
    (A state.json that is not a JSON object at all is another, documented case: load_state reads it as empty.) An unreadable entry
    counts until it falls off the 20 kept, which takes 20 further applies and cannot happen while 3 or more are unreadable (no apply
    can pass the cap), or until a human fixes the file."""
    applied = state.get("applied", [])
    if not isinstance(applied, list):
        return [None] * MAX_APPLIES_PER_DAY
    entries: list[float | None] = []
    for ts in applied:
        try:
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                raise TypeError("not a time")
            age = now - ts
            if age != age:  # NaN
                raise ValueError("not a time")
            if age < 86400:
                entries.append(float(ts))
        except (TypeError, ValueError, OverflowError):
            entries.append(None)
    return entries


def _applies_today(state: dict[str, Any], now: float) -> int:
    """Rule-changing applies in the last 24 h (unreadable entries count, see _window). A text-only apply is not in `applied`: it changes no rule."""
    return len(_window(state, now))


def _next_slot(state: dict[str, Any], now: float) -> str:
    """When the daily cap frees a slot, as text for the printed line and the notice.

    It reports on a run that is already being held back, so it must never raise or change that run: an unreadable entry, or an absurd
    timestamp, ends in "an unknown time". With n applies in the rolling 24 h and a cap of c, a slot is free when the (n-c+1)-th oldest
    of them ages out; for n == c that is the oldest.
    """
    try:
        live = _window(state, now)
        if len(live) < MAX_APPLIES_PER_DAY:
            return "now"
        if any(ts is None for ts in live):
            return "an unknown time"
        live.sort()
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(live[len(live) - MAX_APPLIES_PER_DAY] + 86400))
    except Exception:  # noqa: BLE001
        return "an unknown time"


def _report_deferral(state: dict[str, Any], state_dir: Path, sha: str, slot: str, t: float) -> None:
    """Say, on every capped run, that the cap holds this change back and until when, and log a deferred_cap event. Best-effort: a
    dead stdout or an unwritable events log must not turn a harmless deferral into an exception (the run would skip the notice,
    the metrics and the state save)."""
    _say(f"  daily cap: {MAX_APPLIES_PER_DAY} rule-changing applies in 24h; waits until about {slot}")
    try:
        _log_best_effort(state_dir, {"event": "deferred_cap", "sha": sha, "waits_until": slot, "applied_in_window": _applies_today(state, t)}, t)
    except Exception:  # noqa: BLE001
        pass


VIAS = ("sync_tool", "unknown")


def _bare_etag(etag: str | None) -> str:
    return (etag or "").strip().strip('"')


def _recorded_by_sync_tool(state_dir: Path, before: str, after: str) -> bool:
    """tailscale_policy_sync.py apply records each apply it makes (tps.record_apply). It must have produced the live
    ETag; only when its own re-read failed ("?") is starting from the ETag we last saw enough."""
    try:
        lines = (state_dir / tps.APPLIES_LOG).read_text().splitlines()[-200:]
    except OSError:
        return False
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        produced = _bare_etag(rec.get("etag_after"))
        if produced == _bare_etag(after) or (produced == "?" and _bare_etag(rec.get("etag_before")) == _bare_etag(before)):
            return True
    return False


def _note_live_change(state: dict[str, Any], state_dir: Path, etag: str, notify: Callable[[str, str], None], now: float) -> str | None:
    """A live ETag that differs from the one this reconciler last saw or produced is a change it did not make (a hand
    apply with the sync tool, the admin console, another credential). Counted for the alert, logged, announced once.
    Tailscale's ETag is the sha256 of the stored text, so it only moves when the policy text does."""
    seen = state.get("live_etag")
    state["live_etag"] = etag
    if not seen or _bare_etag(seen) == _bare_etag(etag):
        return None
    via = "sync_tool" if _recorded_by_sync_tool(state_dir, seen, etag) else "unknown"
    counts = state.setdefault("out_of_band", {})
    counts[via] = counts.get(via, 0) + 1
    state["out_of_band_last"] = int(now)
    log_event(state_dir, {"event": "out_of_band_change", "etag_before": seen, "etag_after": etag, "via": via}, now)
    print(f"  OUT OF BAND: the live policy changed from etag {_bare_etag(seen)[:12]} to {_bare_etag(etag)[:12]} and this reconciler did not change it (via {via})")
    notify("tailnet policy: changed outside the reconciler",
           f"The live policy changed (etag {_bare_etag(seen)[:12]} -> {_bare_etag(etag)[:12]}) without a reconciler apply (via {via}). "
           "Live-only rules block the reconciler until git has them; details in the reconcile events log.")
    return via


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
        for via in VIAS:  # both series from the start: increase() cannot see the first sample of a new series
            metrics[f'out_of_band_changes_total{{via="{via}"}}'] = (state.get("out_of_band") or {}).get(via, 0)
        metrics["last_out_of_band_timestamp_seconds"] = state.get("out_of_band_last", 0)
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

    _note_live_change(state, state_dir, etag, notify, now())
    decision = classify(live_text, desired_text, guard)
    integrity_only = bool(problems) and decision.kind != "blocked"  # live and git may agree: what is wrong is the installed code
    if problems:
        decision = Decision("blocked", [*problems, *decision.reasons])
    state["last_sha"] = sha
    # Notices, the failure circuit and the daily cap are keyed on WHAT is waiting (the policy text), not on the commit:
    # main takes many unrelated commits a day, and each one must neither ping again nor reset a circuit.
    policy_id = tps.sha256(tps.normalise_text(desired_text))[:12]
    metrics["git_stored_form"] = 1 if stored_or_none(desired_text) == desired_text else 0
    print(f"reconcile: commit {sha[:12]}, live etag {etag}, decision {decision.kind}, apply {'on' if can_apply else 'off'}")
    for note in decision.reasons if decision.kind == "in_sync" else []:
        print(f"  note: {note}")

    if decision.kind == "text_only" and state.get("unconverged") == policy_id:
        # An apply of exactly this text already left live in another form (neither git's nor tps.stored_form's): a
        # second apply would only repeat it, every run, as #526 did. A human adopts live's text instead.
        decision = Decision("blocked", [
            "applying this text leaves live in a different form (Tailscale re-formats it unlike tailscale_policy_sync.stored_form): "
            "adopt live's text into git (scripts/tailscale-policy-ct108.sh export) and report the formatter difference"
        ])

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
        if integrity_only:
            body = (f"The installed reconciler files could not be confirmed equal to git at {sha[:12]} ({len(problems)} problem(s), "
                    "named in the journal); the live policy is not the problem. Nothing is applied until they match. If a file differs, "
                    "review the merged change, then run scripts/tailscale-policy-reconcile-install.sh from a checkout of origin/main "
                    "(it installs onto the builder). A failed read from git is usually transient; if the same error repeats, see the journal.")
        else:
            body = (f"Merged policy {sha[:12]} differs from live and cannot be applied unattended "
                    f"({len(decision.reasons)} reason(s)). Run scripts/tailscale-policy-ct108.sh plan; details in the reconcile events log.")
        _notice_once(state, key, notify, "tailnet policy: needs a human", body)
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
    if fail.get("policy") == policy_id and fail.get("count", 0) >= CIRCUIT_FAILURES:
        _notice_once(state, f"circuit:{policy_id}", notify, "tailnet policy: reconcile stopped",
                     f"Applying policy {policy_id} failed {fail['count']} times; not retrying until the policy changes.")
        return finish(2, in_sync=0, blocked=1, pending_apply=1)

    if not can_apply:
        why = "PAUSE file present" if paused else "report-only mode"
        print(f"  would apply {decision.added_grants} grant(s) and {decision.added_tests} test(s): {why}")
        log_event(state_dir, {"event": "would_apply", "sha": sha, "why": why}, now())
        if decision.kind == "additive":  # a comment/ordering-only difference is not worth a page
            _notice_once(state, f"would:{policy_id}", notify, "tailnet policy: change waiting",
                         f"{sha[:12]} adds {decision.added_grants} grant(s); not applied ({why}).")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)

    # The cap bounds how many RULE changes land unattended in a day. A text-only apply changes no rule (the semantic
    # diff is empty before, and checked again after), so it neither counts nor waits: counting one spent the cap
    # on 2026-10-20 and left #528 and #533 waiting, which is when they were applied by hand.
    counts = decision.kind == "additive"
    t = now()
    if counts and _applies_today(state, t) >= MAX_APPLIES_PER_DAY:
        slot = _next_slot(state, t)
        _report_deferral(state, state_dir, sha, slot, t)
        _notice_once(state, f"cap:{policy_id}", notify, "tailnet policy: daily cap",
                     f"{MAX_APPLIES_PER_DAY} applies in 24h; {sha[:12]} waits until about {slot}. A hand apply in the meantime is detected and alerted.")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)

    ok, msg = api.validate(desired_text)
    if not ok:
        return _failed(state, state_dir, sha, policy_id, f"validate failed: {msg[:200]}", notify, now, finish)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now()))
    rollback = state_dir / "rollback" / f"policy.{stamp}.{etag.strip(chr(34))[:12]}.hujson"
    tps._write_private(rollback, live_text)
    status, body = api.set_policy(desired_text, etag)
    if status == 412:
        print("  live policy changed while reconciling (ETag): retrying next run")
        return finish(0, in_sync=0, blocked=0, pending_apply=1)
    if status != 200:
        return _failed(state, state_dir, sha, policy_id, f"apply refused: HTTP {status}: {body[:200]}", notify, now, finish)

    after, new_etag = None, "?"  # "?" until a GET has answered; a GET that answered keeps its real ETag even if its body does not parse
    try:
        after, new_etag = api.get_policy()
        left = tps.semantic_diff(tps.parse_hujson(after), tps.parse_hujson(desired_text))
    except Exception as exc:  # noqa: BLE001  the apply itself succeeded; do not lose that fact, whatever the re-read raised
        # (urllib wraps only request errors: a timeout or a dropped connection while reading the answer is not a SyncError). Only a
        # SyncError's text is ours to show; for anything else the class is enough and the message could carry a URL.
        left = [f"could not re-read the live policy: {exc if isinstance(exc, tps.SyncError) else type(exc).__name__}"]
    # What the next run compares against: our own apply is not an out-of-band change. Unknown when the re-read GET itself failed,
    # so the next run takes a fresh baseline instead of guessing; known (the ETag the GET returned) when only its body did not parse.
    state["live_etag"] = new_etag if after is not None else None
    if after is not None and not left and tps.normalise_text(after) not in {
        tps.normalise_text(desired_text), tps.normalise_text(stored_or_none(desired_text) or "")
    }:
        state["unconverged"] = policy_id  # Tailscale stored it in a form we cannot predict: never re-apply it as text-only
    if counts:
        state.setdefault("applied", []).append(int(now()))
        state["applied"] = state["applied"][-20:]
    state["applied_count"] = state.get("applied_count", 0) + 1
    state["last_applied_sha"] = sha
    state["failures"] = {}
    _log_best_effort(state_dir, {"event": "applied", "sha": sha, "kind": decision.kind, "counts_against_cap": counts,
                                 "etag_before": etag, "etag_after": new_etag,
                                 "grants": decision.added_grants, "tests": decision.added_tests, "rollback": str(rollback),
                                 "post_apply_diff": left[:5]}, now())
    notify("tailnet policy: applied", f"Applied {sha[:12]} ({decision.added_grants} grant(s), {decision.added_tests} test(s)). Rollback copy saved.")
    state["notified"] = ""
    _say(f"  applied; new etag {new_etag}; post-apply diff {'EMPTY' if not left else left}")
    return finish(0 if not left else 1, in_sync=1 if not left else 0, blocked=0, pending_apply=0)


def _failed(state, state_dir, sha, policy_id, message, notify, now, finish) -> int:
    fail = state.get("failures") or {}
    count = fail.get("count", 0) + 1 if fail.get("policy") == policy_id else 1
    state["failures"] = {"policy": policy_id, "sha": sha, "count": count}
    print(f"  FAILED: {message}", file=sys.stderr)
    log_event(state_dir, {"event": "apply_failed", "sha": sha, "message": message}, now())
    _notice_once(state, f"fail:{policy_id}:{count}", notify, "tailnet policy: apply failed", f"Applying {sha[:12]} failed (attempt {count}); live policy unchanged.")
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
