"""Self-check runner — ADR 0484.

Reads config/post_conditions.yml, expands template variables against the
active deployment's identity.yml, runs each check via a typed plugin,
emits structured JSON to stdout and a human-readable summary to stderr.

Exit codes:
  0  every critical check passed (non-critical may have failed; warnings shown)
  1  one or more critical checks failed
  2  registry didn't load or didn't schema-validate

Usage:

    # All checks (default tag set):
    uv run --with pyyaml --with jsonschema python scripts/self_check.py

    # Filter to a specific after-step:
    uv run ... python scripts/self_check.py --step converge-harbor

    # Filter to a tag:
    uv run ... python scripts/self_check.py --tag final-smoke

    # Run a specific check id (for debugging):
    uv run ... python scripts/self_check.py --id harbor.registry.public-ping

    # Strict mode — non-critical failures also exit non-zero:
    uv run ... python scripts/self_check.py --strict

Design notes (for tests):

  * `expand_templates(ctx, value)` is pure — no IO.
  * `select_checks(registry, filter_)` is pure — no IO.
  * Each `Check<Type>` plugin is a tiny class with one method, `run(check, ctx)`,
    that returns a CheckResult. IO is encapsulated; the registry runner
    is dependency-injectable so tests can substitute a fake plugin map.
  * `run_check(check, plugins, ctx)` does the retry/backoff loop and
    is the single point of timing/observability.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

# Resolve repo + main-repo (worktree-aware) per ADR 0481 convention.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import REPO_ROOT as MAIN_REPO_ROOT  # noqa: E402
from deployment import load as load_deployment  # noqa: E402
from deployment import resolve_active_slug  # noqa: E402

CODE_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = CODE_ROOT / "config" / "post_conditions.yml"
SCHEMA_PATH = CODE_ROOT / "config" / "contracts" / "deployment-v1" / "post-conditions.schema.json"


# --------------------------------------------------------------------------- #
# Pure helpers (tested directly)
# --------------------------------------------------------------------------- #


@dataclass
class CheckResult:
    check_id: str
    result: str  # "pass" | "fail" | "error"
    critical: bool
    observed: str
    duration_s: float
    attempt: int = 1
    error: str | None = None

    def is_failure(self) -> bool:
        return self.result != "pass"


@dataclass
class RunReport:
    deployment: str
    ran_at: str
    total: int = 0
    passed: int = 0
    failed_critical: int = 0
    failed_warning: int = 0
    errors: int = 0
    results: list[CheckResult] = field(default_factory=list)

    def add(self, r: CheckResult) -> None:
        self.results.append(r)
        self.total += 1
        if r.result == "pass":
            self.passed += 1
        elif r.result == "error":
            self.errors += 1
        elif r.critical:
            self.failed_critical += 1
        else:
            self.failed_warning += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment": self.deployment,
            "ran_at": self.ran_at,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed_critical": self.failed_critical,
                "failed_warning": self.failed_warning,
                "errors": self.errors,
            },
            "results": [asdict(r) for r in self.results],
        }


def build_template_context(identity: dict[str, Any]) -> dict[str, str]:
    """Build the template-substitution context from a deployment identity dict.

    Pure function — no IO. Tested directly.
    """
    apex = (identity.get("platform_domain") or "").strip()
    return {
        "apex": apex,
        "apex_slug": apex.split(".")[0] if apex else "",
        "operator_email": identity.get("platform_operator_email", "") or "",
        "operator_name": identity.get("platform_operator_name", "") or "",
    }


_TEMPLATE_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def expand_templates(ctx: dict[str, str], value: Any) -> Any:
    """Recursively expand `{var}` placeholders in strings using ctx.

    Pure function — no IO. Tested directly.
    """
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            return ctx.get(key, match.group(0))

        return _TEMPLATE_RE.sub(repl, value)
    if isinstance(value, list):
        return [expand_templates(ctx, v) for v in value]
    if isinstance(value, dict):
        return {k: expand_templates(ctx, v) for k, v in value.items()}
    return value


def select_checks(
    registry: dict[str, Any],
    *,
    step: str | None = None,
    tag: str | None = None,
    only_id: str | None = None,
) -> list[dict[str, Any]]:
    """Pick checks from the registry matching the filter.

    Pure function — no IO. Tested directly.
    """
    out = []
    for c in registry.get("post_conditions", []) or []:
        if only_id is not None:
            if c.get("id") == only_id:
                out.append(c)
            continue
        if step is not None and c.get("after_step") != step:
            continue
        if tag is not None and tag not in (c.get("tags") or []):
            continue
        # Default mode: skip bootstrap-only when no filter is set.
        if step is None and tag is None and only_id is None:
            if "bootstrap-only" in (c.get("tags") or []):
                continue
        out.append(c)
    return out


# --------------------------------------------------------------------------- #
# Check-type plugins.
# Each plugin returns (observed: str, ok: bool). The retry loop in
# run_check() decides pass/fail/error based on `ok` and exception flow.
# --------------------------------------------------------------------------- #


class HttpCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        url = c["url"]
        timeout = c.get("timeout_s", 10)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = resp.status
                body = resp.read(2048).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status = e.code
            body = ""
        ok = True
        if "expect_status" in c and status != c["expect_status"]:
            ok = False
        if "expect_body_contains" in c and c["expect_body_contains"] not in body:
            ok = False
        return f"GET {url} -> {status}", ok


class TcpCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        host, port = c["host"], int(c["port"])
        timeout = c.get("timeout_s", 5)
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(timeout)
            s.connect((host, port))
        return f"TCP {host}:{port} connected", True


class TlsCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        host, port = c["host"], int(c.get("port", 443))
        timeout = c.get("timeout_s", 10)
        ctx_tls = ssl.create_default_context()
        with contextlib.closing(socket.create_connection((host, port), timeout=timeout)) as raw:
            with ctx_tls.wrap_socket(raw, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        sans = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
        ok = True
        notes = []
        if "expect_san" in c:
            missing = [s for s in c["expect_san"] if s not in sans]
            if missing:
                ok = False
                notes.append(f"missing SANs: {missing}")
        if "expect_days_remaining" in c:
            not_after = cert.get("notAfter")
            if not_after:
                exp = _dt.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days = (exp - _dt.datetime.utcnow()).days
                notes.append(f"{days}d remaining")
                if days < c["expect_days_remaining"]:
                    ok = False
        return f"TLS {host}:{port} SAN={sans[:3]}{'…' if len(sans) > 3 else ''} {' '.join(notes)}", ok


class DnsCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        record = c["record"]
        rtype = c.get("record_type", "A")
        result = subprocess.run(
            ["dig", "+short", record, rtype],
            capture_output=True,
            text=True,
            timeout=c.get("timeout_s", 5),
        )
        answers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        ok = True
        expect = c.get("expect_value")
        if expect == "present":
            ok = bool(answers)
        elif expect:
            ok = expect in answers
        return f"DNS {rtype} {record} -> {answers}", ok


class FileCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        path = Path(c["path"])
        exists = path.is_file()
        ok = True
        notes = [f"exists={exists}"]
        if "expect_exists" in c and exists != c["expect_exists"]:
            ok = False
        if exists and "expect_regex" in c:
            text = path.read_text()
            m = re.search(c["expect_regex"], text)
            notes.append(f"regex={'hit' if m else 'miss'}")
            if not m:
                ok = False
        if exists and "expect_sha256" in c:
            import hashlib

            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            notes.append(f"sha256={actual[:12]}…")
            if actual != c["expect_sha256"]:
                ok = False
        return f"file {path} {' '.join(notes)}", ok


class CommandCheck:
    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        cmd = c["command"]
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=c.get("timeout_s", 30),
        )
        ok = result.returncode == c.get("expect_exit", 0)
        if "expect_stdout" in c and c["expect_stdout"] not in result.stdout:
            ok = False
        return f"exit={result.returncode} stdout={result.stdout[:100]!r}", ok


class DockerCheck:
    """Inspects a container on a remote host over SSH (via the host alias)."""

    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        ssh_target = c.get("via_ssh")
        if not ssh_target:
            return "no via_ssh declared", False
        # Build remote inspect command. Tolerate ssh_mosh_logger noise.
        container = c["container"]
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            ssh_target,
            f"sudo docker inspect --format '{{{{.State.Status}}}}|{{{{.State.Health.Status}}}}' {container}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=c.get("timeout_s", 20))
        line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        status, _, health = line.partition("|")
        ok = True
        if c.get("expect_running") and status != "running":
            ok = False
        want_health = c.get("expect_health", "any")
        if want_health != "any" and health and health != want_health:
            ok = False
        return f"{container} status={status} health={health or 'n/a'}", ok


class PveapiCheck:
    """Lightweight Proxmox-host inspection over SSH to the jump host."""

    def run(self, c: dict[str, Any], ctx: dict[str, str]) -> tuple[str, bool]:
        ssh_target = c.get("via_ssh")
        if not ssh_target:
            return "no via_ssh declared", False
        cmd = c.get("command") or "qm list"
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_target, cmd],
            capture_output=True,
            text=True,
            timeout=c.get("timeout_s", 30),
        )
        ok = result.returncode == 0
        if "expect_stdout" in c and c["expect_stdout"] not in result.stdout:
            ok = False
        return f"pveapi {ssh_target}: rc={result.returncode}", ok


DEFAULT_PLUGINS: dict[str, Any] = {
    "http": HttpCheck(),
    "tcp": TcpCheck(),
    "tls": TlsCheck(),
    "dns": DnsCheck(),
    "file": FileCheck(),
    "command": CommandCheck(),
    "docker": DockerCheck(),
    "pveapi": PveapiCheck(),
}


# --------------------------------------------------------------------------- #
# Retry loop (the single timing/observability point)
# --------------------------------------------------------------------------- #


def run_check(
    check: dict[str, Any],
    plugins: dict[str, Any],
    ctx: dict[str, str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CheckResult:
    """Run a single check with retry/backoff. Returns a CheckResult.

    Injectable `sleep` + `clock` make this testable without real waits.
    """
    plugin = plugins.get(check["type"])
    if plugin is None:
        return CheckResult(
            check_id=check["id"],
            result="error",
            critical=check.get("critical", True),
            observed=f"unknown check type {check['type']!r}",
            duration_s=0.0,
            error=f"no plugin for type {check['type']}",
        )

    expanded = expand_templates(ctx, check)
    retries = int(check.get("retries", 0))
    backoff = float(check.get("retry_backoff_s", 1.0))
    attempt = 0
    start = clock()
    last_err: str | None = None
    observed = ""
    ok = False

    while attempt <= retries:
        attempt += 1
        try:
            observed, ok = plugin.run(expanded, ctx)
            if ok:
                return CheckResult(
                    check_id=check["id"],
                    result="pass",
                    critical=check.get("critical", True),
                    observed=observed,
                    duration_s=clock() - start,
                    attempt=attempt,
                )
        except Exception as e:  # noqa: BLE001 - plugins surface arbitrary errors
            last_err = f"{type(e).__name__}: {e}"
            observed = f"exception during check: {last_err}"
        if attempt <= retries:
            sleep(backoff)

    return CheckResult(
        check_id=check["id"],
        result="fail" if last_err is None else "error",
        critical=check.get("critical", True),
        observed=observed,
        duration_s=clock() - start,
        attempt=attempt,
        error=last_err,
    )


# --------------------------------------------------------------------------- #
# Registry loader + entry point
# --------------------------------------------------------------------------- #


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        sys.exit(f"registry not found: {path}")
    with path.open() as f:
        registry = yaml.safe_load(f) or {}
    # Best-effort schema validate.
    try:
        from jsonschema import Draft202012Validator  # type: ignore

        if SCHEMA_PATH.is_file():
            schema = json.loads(SCHEMA_PATH.read_text())
            errs = list(Draft202012Validator(schema).iter_errors(registry))
            if errs:
                msgs = ["  " + (".".join(str(p) for p in e.absolute_path) or "<root>") + ": " + e.message for e in errs]
                sys.exit("post-conditions registry failed schema validation:\n" + "\n".join(msgs))
    except ImportError:
        pass
    return registry


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", help="Filter to checks whose after_step matches")
    p.add_argument("--tag", help="Filter to checks tagged with this tag")
    p.add_argument("--id", dest="only_id", help="Run a single check by id")
    p.add_argument("--strict", action="store_true", help="Non-critical failures also exit non-zero")
    p.add_argument("--json", action="store_true", help="Emit only JSON to stdout (no stderr summary)")
    p.add_argument("--registry", default=str(REGISTRY_PATH), help="Path to post_conditions.yml")
    args = p.parse_args()

    try:
        slug = resolve_active_slug()
    except Exception as e:
        sys.stderr.write(f"deployment not resolved: {e}\n")
        return 2

    deployment = load_deployment(slug)
    ctx = build_template_context(deployment.identity)

    registry = load_registry(Path(args.registry))
    selected = select_checks(registry, step=args.step, tag=args.tag, only_id=args.only_id)

    report = RunReport(deployment=slug, ran_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for c in selected:
        result = run_check(c, DEFAULT_PLUGINS, ctx)
        report.add(result)
        if not args.json:
            badge = {"pass": "PASS", "fail": "FAIL", "error": "ERR "}[result.result]
            crit = "CRIT" if result.critical else "warn"
            sys.stderr.write(f"  [{badge}] [{crit}] {result.check_id:<40} {result.observed}\n")

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        s = report
        sys.stderr.write(
            f"\nself-check: {s.passed}/{s.total} passed, "
            f"{s.failed_critical} critical fail, {s.failed_warning} warning, {s.errors} errors\n"
        )

    if report.failed_critical or report.errors:
        return 1
    if args.strict and report.failed_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
