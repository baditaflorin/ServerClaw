#!/usr/bin/env python3
"""Manage the SaaS Tailscale tailnet policy as code (config/tailscale/policy.hujson).

Subcommands
-----------
check    Offline only, no credentials, no network. HuJSON syntax, forbidden patterns (allow-all, tags missing from
         tagOwners) and the lockout guard (policy tests must keep proving the operator Mac and the bastions can SSH).
         This is what CI runs.
export   GET the live policy (HuJSON, comments preserved) to stdout; the ETag goes to stderr.
plan     GET live, diff against the file (semantic + text), run `check`, POST /acl/validate (which also runs the
         policy `tests`). Records the live ETag and hashes in a plan file for `apply`. Exit non-zero on any failure.
apply    Re-checks that the plan is fresh, that the file and the live policy are unchanged since the plan, saves the
         pre-apply policy as a rollback copy, then POSTs with `If-Match: <etag>` so a concurrent edit is refused.
drift    GET live, compare with the file, optionally write node-exporter textfile metrics. Exit 2 on drift, 3 on error.

Credentials are never stored in git or printed. The OAuth client (JSON with client_id/client_secret) is fetched at run
time from the fleet vault secret `tailscale_policy_oauth_client` through /root/bin/fleet-vault.py on CT108, run under
the systemd-run credential wrapper documented in that script (override with TS_POLICY_CRED_CMD for another provider).
Only python3 stdlib is used.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = os.environ.get("TS_API_BASE", "https://api.tailscale.com/api/v2")
TAILNET = os.environ.get("TS_TAILNET", "-")
VAULT_SECRET = "tailscale_policy_oauth_client"
DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "config" / "tailscale" / "policy.hujson"
DEFAULT_GUARD = DEFAULT_POLICY.with_name("lockout-guard.json")
PUBLICATION_MANIFEST = Path(__file__).resolve().parents[1] / "config" / "publication-sanitization.yaml"
DEFAULT_STATE_DIR = Path(os.environ.get("TS_POLICY_STATE_DIR", "/var/lib/tailscale-policy-sync"))
DEFAULT_TEXTFILE_DIR = Path("/var/lib/prometheus/node-exporter")
PLAN_MAX_AGE_SECONDS = 900

# The documented systemd-run credential wrapper from /root/bin/fleet-vault.py (CT108). `fleet-vault.py raw` is the
# fleet-runner consumer path; it refuses to print to a tty, so the secret only ever travels through a pipe.
VAULT_CMD = [
    "systemd-run",
    "--wait",
    "--collect",
    "--pipe",
    "-p",
    "User=root",
    "-p",
    "LoadCredentialEncrypted=apikey-service-admin-token:"
    "/etc/credstore.encrypted/fleet-graph-writer-renew/current/apikey-service-admin-token.cred",
    "-p",
    "LoadCredentialEncrypted=fleet-secrets-admin-token:"
    "/etc/credstore.encrypted/fleet-runner-woodpecker-rotation/current/fleet-secrets-admin-token.cred",
    "-E",
    "HOME=/root",
    "/root/bin/fleet-vault.py",
    "raw",
    VAULT_SECRET,
]

TAG_RE = re.compile(r"tag:[A-Za-z0-9_-]+")


class SyncError(Exception):
    """A failure the operator must act on (message is safe to print)."""


# ---------------------------------------------------------------------------------------------------------------
# HuJSON handling
# ---------------------------------------------------------------------------------------------------------------


def standardize_hujson(text: str) -> str:
    """Return plain JSON for a HuJSON document: comments and trailing commas removed, strings untouched."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            if j >= n:
                raise SyncError("unterminated string in policy")
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j  # keep the newline
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j == -1:
                raise SyncError("unterminated block comment in policy")
            out.append(" ")
            i = j + 2
        else:
            out.append(c)
            i += 1
    stripped = "".join(out)
    # Trailing commas: a comma followed only by whitespace and then a closer. Strings were copied verbatim above, so
    # run this on a copy where string contents are masked, then splice by position.
    masked = re.sub(r'"(?:[^"\\]|\\.)*"', lambda m: '"' + "x" * (len(m.group(0)) - 2) + '"', stripped)
    drop = [m.start() for m in re.finditer(r",(?=\s*[}\]])", masked)]
    if drop:
        chars = list(stripped)
        for pos in drop:
            chars[pos] = " "
        stripped = "".join(chars)
    return stripped


def parse_hujson(text: str) -> Any:
    try:
        return json.loads(standardize_hujson(text))
    except json.JSONDecodeError as exc:
        raise SyncError(f"policy is not valid HuJSON: {exc}") from exc


def normalise_text(text: str) -> str:
    """Line-ending and trailing-newline normalisation only; comments and ordering are significant."""
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# Diffing
# ---------------------------------------------------------------------------------------------------------------


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def semantic_diff(live: Any, desired: Any, path: str = "") -> list[str]:
    """Human-readable differences between two parsed policies ("-" = only live, "+" = only in git)."""
    if _canon(live) == _canon(desired):
        return []
    here = path or "<policy>"
    if isinstance(live, dict) and isinstance(desired, dict):
        lines: list[str] = []
        for key in sorted(set(live) | set(desired)):
            sub = f"{path}.{key}" if path else key
            if key not in desired:
                lines.append(f"- {sub}: {_canon(live[key])}")
            elif key not in live:
                lines.append(f"+ {sub}: {_canon(desired[key])}")
            else:
                lines.extend(semantic_diff(live[key], desired[key], sub))
        return lines
    if isinstance(live, list) and isinstance(desired, list):
        live_items = [_canon(x) for x in live]
        want_items = [_canon(x) for x in desired]
        lines = []
        remaining = list(want_items)
        only_live = []
        for item in live_items:
            if item in remaining:
                remaining.remove(item)
            else:
                only_live.append(item)
        lines.extend(f"- {here}[]: {item}" for item in only_live)
        lines.extend(f"+ {here}[]: {item}" for item in remaining)
        if not only_live and not remaining:
            lines.append(f"~ {here}: same items, different order")
        return lines
    return [f"~ {here}: live={_canon(live)} git={_canon(desired)}"]


def text_diff(live_text: str, desired_text: str) -> list[str]:
    return list(
        difflib.unified_diff(
            normalise_text(live_text).splitlines(),
            normalise_text(desired_text).splitlines(),
            fromfile="live (tailnet)",
            tofile="git (policy.hujson)",
            lineterm="",
        )
    )


# ---------------------------------------------------------------------------------------------------------------
# Offline checks
# ---------------------------------------------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)


def forbidden_pattern_errors(policy: dict[str, Any]) -> list[str]:
    """No allow-all rule: wildcard source reaching wildcard destination on all ports."""
    errors: list[str] = []
    for idx, rule in enumerate(_as_list(policy.get("acls"))):
        if not isinstance(rule, dict) or rule.get("action", "accept") != "accept":
            continue
        src = _as_list(rule.get("src"))
        dst = _as_list(rule.get("dst"))
        if "*" in src and any(d in ("*", "*:*") for d in dst):
            errors.append(f'acls[{idx}] is an allow-all rule ("*" -> "*:*"); forbidden')
    for idx, rule in enumerate(_as_list(policy.get("grants"))):
        if not isinstance(rule, dict):
            continue
        src = _as_list(rule.get("src"))
        dst = _as_list(rule.get("dst"))
        ips = _as_list(rule.get("ip"))
        if "*" in src and "*" in dst and ("*" in ips or "*:*" in ips or (not ips and "app" not in rule)):
            errors.append(f'grants[{idx}] is an allow-all grant ("*" -> "*" on all ports); forbidden')
    return errors


def tag_errors(policy: dict[str, Any]) -> list[str]:
    """Every tag referenced anywhere (rules, tests, ssh, autoApprovers, owners) must exist in tagOwners."""
    owners = policy.get("tagOwners")
    if not isinstance(owners, dict):
        return ["policy has no tagOwners object"]
    defined = set(owners)
    errors: list[str] = []
    for key, value in policy.items():
        if key == "tagOwners":
            scan = [s for owner in owners.values() for s in _strings(owner)]
        else:
            scan = list(_strings(value))
        for text in scan:
            for tag in TAG_RE.findall(text):
                if tag not in defined:
                    errors.append(f"{tag} is referenced in '{key}' but missing from tagOwners")
    return sorted(set(errors))


def load_guard(guard_path: Path) -> dict[str, Any]:
    try:
        return json.loads(guard_path.read_text())
    except FileNotFoundError as exc:
        raise SyncError(f"lockout guard file missing: {guard_path}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError(f"lockout guard file is not valid JSON: {exc}") from exc


def _test_accepts(policy: dict[str, Any]) -> set[tuple[str, str]]:
    """(src, dst) pairs the policy `tests` assert as reachable (accept)."""
    pairs: set[tuple[str, str]] = set()
    for test in _as_list(policy.get("tests")):
        if not isinstance(test, dict):
            continue
        src = test.get("src")
        for dst in _as_list(test.get("accept")):
            if isinstance(src, str) and isinstance(dst, str):
                pairs.add((src, dst))
    return pairs


def lockout_guard_errors(policy: dict[str, Any], guard: dict[str, Any]) -> list[str]:
    """The policy must keep tests proving the Mac and the bastions can SSH (:22). The API enforces policy tests, so a
    policy edit that would lock those paths out is rejected by plan/apply, but only if the tests are still present."""
    errors: list[str] = []
    required = _as_list(guard.get("required_accept"))
    if not required:
        return ["lockout guard lists no required_accept entries"]
    have = _test_accepts(policy)
    for item in required:
        src, dst, why = item.get("src"), item.get("dst"), item.get("why", "")
        if (src, dst) not in have:
            errors.append(f"lockout guard: policy tests no longer prove {src} -> {dst} ({why})")
    return errors


def check_policy(text: str, guard: dict[str, Any]) -> list[str]:
    """All offline checks; returns a list of error strings (empty = pass)."""
    try:
        policy = parse_hujson(text)
    except SyncError as exc:
        return [str(exc)]
    if not isinstance(policy, dict):
        return ["policy root must be an object"]
    errors: list[str] = []
    errors.extend(forbidden_pattern_errors(policy))
    errors.extend(tag_errors(policy))
    errors.extend(lockout_guard_errors(policy, guard))
    if not _as_list(policy.get("tests")):
        errors.append("policy has no `tests`; refusing a policy that cannot prove anything")
    if not _as_list(policy.get("grants")) and not _as_list(policy.get("acls")):
        errors.append("policy has neither grants nor acls")
    return errors


# ---------------------------------------------------------------------------------------------------------------
# Tailscale API
# ---------------------------------------------------------------------------------------------------------------


def fetch_oauth_client() -> dict[str, str]:
    override = os.environ.get("TS_POLICY_CRED_CMD")
    cmd = override.split() if override else VAULT_CMD
    try:
        res = subprocess.run(cmd, capture_output=True, check=False, timeout=90)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError(
            f"could not run the vault credential command ({type(exc).__name__}); run this on CT108"
        ) from exc
    if res.returncode != 0:
        # stderr of fleet-vault never contains the secret value; still keep it short.
        raise SyncError("vault credential fetch failed: " + res.stderr.decode(errors="replace").strip()[:200])
    try:
        client = json.loads(res.stdout.decode())
        return {"client_id": client["client_id"], "client_secret": client["client_secret"]}
    except (ValueError, KeyError) as exc:
        raise SyncError("vault secret is not the expected JSON {client_id, client_secret}") from exc


class TailscaleAPI:
    def __init__(self, token: str) -> None:
        self._token = token

    @classmethod
    def login(cls) -> "TailscaleAPI":
        client = fetch_oauth_client()
        body = urllib.parse.urlencode({**client, "grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(API_BASE + "/oauth/token", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return cls(json.loads(resp.read())["access_token"])
        except urllib.error.HTTPError as exc:
            raise SyncError(f"OAuth token exchange failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            raise SyncError(f"OAuth token exchange failed: {type(exc).__name__}") from exc

    def _request(self, method: str, path: str, body: str | None = None, headers: dict[str, str] | None = None):
        hdrs = {"Authorization": f"Bearer {self._token}", "Accept": "application/hujson"}
        hdrs.update(headers or {})
        data = body.encode() if body is not None else None
        req = urllib.request.Request(f"{API_BASE}/tailnet/{TAILNET}{path}", data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                return resp.status, resp.read().decode(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(errors="replace"), dict(exc.headers)
        except urllib.error.URLError as exc:
            raise SyncError(f"Tailscale API unreachable: {exc.reason}") from exc

    def get_policy(self) -> tuple[str, str]:
        status, body, headers = self._request("GET", "/acl")
        if status != 200:
            raise SyncError(f"GET /acl failed: HTTP {status}: {body[:200]}")
        etag = next((v for k, v in headers.items() if k.lower() == "etag"), "")
        if not etag:
            raise SyncError("GET /acl returned no ETag; cannot do a safe apply")
        return body, etag

    def validate(self, text: str) -> tuple[bool, str]:
        status, body, _ = self._request("POST", "/acl/validate", text, {"Content-Type": "application/hujson"})
        if status == 200 and body.strip() in ("", "{}"):
            return True, "valid; policy tests pass"
        return False, f"HTTP {status}: {body[:1500]}"

    def set_policy(self, text: str, etag: str) -> tuple[int, str]:
        status, body, _ = self._request("POST", "/acl", text, {"Content-Type": "application/hujson", "If-Match": etag})
        return status, body[:1500]


# ---------------------------------------------------------------------------------------------------------------
# State (plan file)
# ---------------------------------------------------------------------------------------------------------------


def _state_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "plan.json", state_dir / "plan.live.hujson"


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def write_textfile(textfile_dir: Path, lines: list[str]) -> Path:
    textfile_dir.mkdir(parents=True, exist_ok=True)
    final = textfile_dir / "tailscale_policy.prom"
    fd, tmp = tempfile.mkstemp(dir=textfile_dir, prefix=".tailscale_policy.")
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, final)
    return final


def metric_lines(*, ok: bool, semantic: bool, text: bool, now: float) -> list[str]:
    lines = [
        "# HELP tailscale_policy_check_success 1 if the last live-policy comparison completed.",
        "# TYPE tailscale_policy_check_success gauge",
        f"tailscale_policy_check_success {1 if ok else 0}",
    ]
    if ok:
        lines += [
            "# HELP tailscale_policy_drift 1 if the live tailnet policy differs from config/tailscale/policy.hujson.",
            "# TYPE tailscale_policy_drift gauge",
            f'tailscale_policy_drift{{kind="semantic"}} {1 if semantic else 0}',
            f'tailscale_policy_drift{{kind="text"}} {1 if text else 0}',
            "# HELP tailscale_policy_last_check_timestamp_seconds Unix time of the last successful comparison.",
            "# TYPE tailscale_policy_last_check_timestamp_seconds gauge",
            f"tailscale_policy_last_check_timestamp_seconds {int(now)}",
        ]
    return lines


# ---------------------------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------------------------


def _read_policy(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise SyncError(f"policy file not found: {path}") from exc


def cmd_check(args: argparse.Namespace) -> int:
    # The public ServerClaw publisher removes both the private tailnet policy and
    # its sanitization manifest. Skip this check only for that known snapshot
    # shape; a missing policy in the private source repository remains an error.
    if args.file == DEFAULT_POLICY and not args.file.exists() and not PUBLICATION_MANIFEST.exists():
        print("check: skipped (private Tailscale policy is omitted from this sanitized snapshot)")
        return 0
    errors = check_policy(_read_policy(args.file), load_guard(args.guard))
    for err in errors:
        print(f"FAIL {err}", file=sys.stderr)
    print("check: " + ("FAILED" if errors else f"ok ({args.file})"))
    return 1 if errors else 0


def cmd_export(args: argparse.Namespace) -> int:
    text, etag = TailscaleAPI.login().get_policy()
    sys.stdout.write(text)
    print(f"etag={etag}", file=sys.stderr)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    desired = _read_policy(args.file)
    guard = load_guard(args.guard)
    errors = check_policy(desired, guard)
    for err in errors:
        print(f"FAIL offline check: {err}", file=sys.stderr)
    api = TailscaleAPI.login()
    live, etag = api.get_policy()

    try:
        sem = semantic_diff(parse_hujson(live), parse_hujson(desired))
    except SyncError:
        sem = []  # the offline check above already reported the syntax error
    txt = text_diff(live, desired)
    print(f"live etag: {etag}")
    if sem:
        print("semantic changes (- live only, + git only):")
        print("\n".join(f"  {line}" for line in sem))
    if txt:
        kind = "text/comment-only difference" if not sem else "text diff"
        print(f"{kind}:")
        print("\n".join(txt))
    if not sem and not txt:
        print("no differences: live policy is identical to the file")

    ok_validate, msg = api.validate(desired)
    print(f"validate + policy tests: {'ok' if ok_validate else 'FAILED'} ({msg})")
    ok = ok_validate and not errors

    plan_file, live_copy = _state_paths(args.state_dir)
    if ok:
        _write_private(live_copy, live)
        _write_private(
            plan_file,
            json.dumps(
                {
                    "etag": etag,
                    "live_sha256": sha256(live),
                    "file_sha256": sha256(desired),
                    "file": str(args.file),
                    "created": time.time(),
                    "changes": bool(sem or txt),
                },
                indent=2,
            ),
        )
        print(f"plan saved: {plan_file} (valid {PLAN_MAX_AGE_SECONDS // 60} min)")
    else:
        plan_file.unlink(missing_ok=True)
        print("plan FAILED; no plan recorded, apply will refuse", file=sys.stderr)
        return 1
    if args.detailed_exitcode and (sem or txt):
        return 2
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    plan_file, live_copy = _state_paths(args.state_dir)
    if not plan_file.exists():
        raise SyncError("no plan on record: run `plan` first")
    plan = json.loads(plan_file.read_text())
    age = time.time() - plan["created"]
    if age > args.max_age:
        raise SyncError(f"plan is {int(age)}s old (max {args.max_age}s): re-run `plan`")
    desired = _read_policy(args.file)
    if sha256(desired) != plan["file_sha256"]:
        raise SyncError("the policy file changed since the plan: re-run `plan`")
    if not plan.get("changes"):
        print("nothing to apply: the plan showed no differences")
        return 0
    errors = check_policy(desired, load_guard(args.guard))
    if errors:
        raise SyncError("offline check failed: " + "; ".join(errors))
    if not args.yes:
        if input(f"Apply {args.file} to the live tailnet policy? Type 'apply' to continue: ").strip() != "apply":
            raise SyncError("aborted by operator")

    api = TailscaleAPI.login()
    live, etag = api.get_policy()
    if etag != plan["etag"] or sha256(live) != plan["live_sha256"]:
        raise SyncError("the live policy changed since the plan (ETag mismatch): re-run `plan` and review the diff")
    ok, msg = api.validate(desired)
    if not ok:
        raise SyncError(f"validate failed: {msg}")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rollback = args.state_dir / "rollback" / f"policy.{stamp}.{plan['etag'].strip(chr(34))[:12]}.hujson"
    _write_private(rollback, live)
    print(f"rollback copy saved: {rollback}")

    status, body = api.set_policy(desired, etag)
    if status != 200:
        raise SyncError(f"apply refused: HTTP {status}: {body}  (live policy unchanged)")
    plan_file.unlink(missing_ok=True)
    print("applied. verifying round trip ...")
    after, new_etag = api.get_policy()
    left = semantic_diff(parse_hujson(after), parse_hujson(desired))
    print(f"new etag: {new_etag}; post-apply semantic diff: {'EMPTY' if not left else left}")
    print(f"rollback: scripts/tailscale_policy_sync.py plan --file {rollback} && ... apply --file {rollback}")
    return 0 if not left else 1


def cmd_drift(args: argparse.Namespace) -> int:
    now = time.time()
    try:
        desired = _read_policy(args.file)
        live, etag = TailscaleAPI.login().get_policy()
        sem = semantic_diff(parse_hujson(live), parse_hujson(desired))
        txt = text_diff(live, desired)
    except SyncError as exc:
        print(f"drift: ERROR {exc}", file=sys.stderr)
        if args.textfile_dir:
            write_textfile(args.textfile_dir, metric_lines(ok=False, semantic=False, text=False, now=now))
        return 3
    if args.textfile_dir:
        path = write_textfile(args.textfile_dir, metric_lines(ok=True, semantic=bool(sem), text=bool(txt), now=now))
        print(f"metrics written: {path}")
    if sem or txt:
        print(f"DRIFT: live policy (etag {etag}) differs from {args.file}")
        print("\n".join(sem or ["(comment/format-only difference)"]))
        return 2
    print(f"no drift (etag {etag})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--file", type=Path, default=DEFAULT_POLICY, help="policy file (default: %(default)s)")
        p.add_argument("--guard", type=Path, default=DEFAULT_GUARD, help="lockout guard (default: %(default)s)")

    p = sub.add_parser("check", help="offline checks (no credentials)")
    common(p)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("export", help="print the live policy (HuJSON) to stdout")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("plan", help="diff + validate + policy tests against the live tailnet (read-only)")
    common(p)
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--detailed-exitcode", action="store_true", help="exit 2 when the plan has changes")
    p.set_defaults(func=cmd_plan)
    p = sub.add_parser("apply", help="apply the planned policy (ETag-guarded)")
    common(p)
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--max-age", type=int, default=PLAN_MAX_AGE_SECONDS)
    p.add_argument("--yes", action="store_true", help="do not prompt")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("drift", help="compare live with git; write node-exporter textfile metrics")
    common(p)
    p.add_argument("--textfile-dir", type=Path, nargs="?", const=DEFAULT_TEXTFILE_DIR, default=None)
    p.set_defaults(func=cmd_drift)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)
    try:
        return args.func(args)
    except SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
