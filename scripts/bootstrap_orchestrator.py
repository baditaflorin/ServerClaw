"""Bootstrap orchestrator — ADR 0483 §4.

Drives the 14-step gated bootstrap chain defined in config/bootstrap_steps.yml.
Each step is executed by invoking its `make_target` via `make`. Before each
step the orchestrator evaluates preconditions; after, it evaluates
postconditions. Failures are classified per `gates.fail_fast` from the
active deployment's manifest.yml.

Receipts are written to receipts/bootstrap/:
  <timestamp>-<slug>-bootstrap-receipt.json    (success)
  <timestamp>-<slug>-<step-id>-failure.json    (per-step failure)

Exit codes:
  0  all steps completed and postconditions passed
  1  one or more steps failed
  2  configuration error (missing manifest, bad schema, etc.)

Usage:

    # Full run:
    uv run --with pyyaml --with jsonschema python scripts/bootstrap_orchestrator.py

    # Resume from a specific step (skip earlier steps):
    uv run ... python scripts/bootstrap_orchestrator.py --resume-from 3-init-remote

    # Status only (no execution):
    uv run ... python scripts/bootstrap_orchestrator.py --status

    # Dry-run (print steps, do not execute make targets):
    uv run ... python scripts/bootstrap_orchestrator.py --dry-run

Pure helpers (select_steps, evaluate_condition, step_status) are tested directly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"
IDENTITY_PATH = LOCAL_ROOT / "identity.yml"
MANIFEST_PATH = LOCAL_ROOT / "manifest.yml"
STEPS_PATH = REPO_ROOT / "config" / "bootstrap_steps.yml"
POST_CONDITIONS_PATH = REPO_ROOT / "config" / "post_conditions.yml"
RECEIPTS_DIR = REPO_ROOT / "receipts" / "bootstrap"


def _load_identity() -> dict[str, Any]:
    """Read .local/identity.yml (ADR 0385 + ADR 0488 — single deployment per repo)."""
    if not IDENTITY_PATH.is_file():
        return {}
    with IDENTITY_PATH.open() as f:
        return yaml.safe_load(f) or {}


# Conditions whose types require no live IO and are always evaluated locally.
_LOCAL_CONDITION_TYPES = {"file", "schema"}


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass
class ConditionResult:
    condition_id: str
    ok: bool
    observed: str
    error: str | None = None


@dataclass
class StepResult:
    step_id: str
    make_target: str
    status: str  # "skipped" | "passed" | "failed" | "error"
    precondition_results: list[ConditionResult] = field(default_factory=list)
    postcondition_results: list[ConditionResult] = field(default_factory=list)
    make_exit_code: int | None = None
    make_stdout: str = ""
    make_stderr: str = ""
    duration_s: float = 0.0
    retries_used: int = 0
    error: str | None = None

    def failed_preconditions(self) -> list[ConditionResult]:
        return [c for c in self.precondition_results if not c.ok]

    def failed_postconditions(self) -> list[ConditionResult]:
        return [c for c in self.postcondition_results if not c.ok]


@dataclass
class BootstrapReceipt:
    schema_version: int
    receipt_id: str
    deployment: str
    ran_at: str
    outcome: str  # "success" | "failure" | "partial"
    steps_attempted: int
    steps_passed: int
    steps_failed: int
    steps_skipped: int
    resume_from: str | None
    step_results: list[StepResult] = field(default_factory=list)
    failed_step_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["step_results"] = [asdict(r) for r in self.step_results]
        return d


# --------------------------------------------------------------------------- #
# Pure helpers (tested directly)
# --------------------------------------------------------------------------- #


def select_steps(
    steps: list[dict[str, Any]],
    *,
    resume_from: str | None = None,
) -> list[dict[str, Any]]:
    """Return the steps to execute, honoring resume_from.

    If resume_from is given, all steps before it are skipped (returned with
    status="skipped"). The matching step and all subsequent steps are included.

    Pure function — no IO. Tested directly.
    """
    if resume_from is None:
        return list(steps)
    ids = [s["id"] for s in steps]
    if resume_from not in ids:
        raise ValueError(f"resume-from step {resume_from!r} not found in bootstrap_steps.yml")
    idx = ids.index(resume_from)
    return list(steps[idx:])


def build_template_ctx(identity: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, str]:
    """Build the template context for substitution into preconditions/postconditions.

    Pure function — no IO. Tested directly.

    Variables exposed (when sources are present):
      {apex}                  -- identity.platform_domain
      {apex_slug}             -- first label of apex
      {provider_host}         -- manifest.provider.host
      {provider_port}         -- manifest.provider.port (default 22)
      {provider_user}         -- manifest.provider.initial_user
      {initial_key_filename}  -- manifest.provider.initial_key_path
    """
    apex = identity.get("platform_domain", "")
    apex_slug = apex.split(".")[0] if apex else ""
    ctx: dict[str, str] = {"apex": apex, "apex_slug": apex_slug}
    if manifest:
        provider = manifest.get("provider") or {}
        if "host" in provider:
            ctx["provider_host"] = str(provider["host"])
        ctx["provider_port"] = str(provider.get("port", 22))
        if "initial_user" in provider:
            ctx["provider_user"] = str(provider["initial_user"])
        if "initial_key_path" in provider:
            ctx["initial_key_filename"] = str(provider["initial_key_path"])
    return ctx


def expand_templates(ctx: dict[str, str], value: Any) -> Any:
    """Recursively expand {var} placeholders.

    Pure function — no IO. Tested directly.
    """
    import re

    _re = re.compile(r"\{(\w+)\}")
    if isinstance(value, str):
        return _re.sub(lambda m: ctx.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [expand_templates(ctx, v) for v in value]
    if isinstance(value, dict):
        return {k: expand_templates(ctx, v) for k, v in value.items()}
    return value


def evaluate_condition(
    condition: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> ConditionResult:
    """Evaluate a single precondition or postcondition dict.

    Supports types: file, schema, command.
    Returns a ConditionResult. Pure-ish: file/schema checks have IO but no
    side effects; command type spawns a subprocess.

    Tested directly (with tmp_path fixtures for file/schema types).
    """
    cid = condition.get("id", "unknown")
    ctype = condition.get("type", "")

    try:
        if ctype == "file":
            path = repo_root / condition["path"]
            exists = path.is_file() or path.is_dir()
            expected = condition.get("expect_exists", True)
            ok = exists == expected
            observed = f"{'exists' if exists else 'missing'}: {path}"
            return ConditionResult(cid, ok, observed)

        if ctype == "schema":
            try:
                import jsonschema
            except ImportError:
                return ConditionResult(cid, False, "jsonschema not installed", error="import error")
            target_path = repo_root / condition["target"]
            schema_path = repo_root / condition["schema"]
            if not target_path.is_file():
                return ConditionResult(cid, False, f"target not found: {target_path}")
            if not schema_path.is_file():
                return ConditionResult(cid, False, f"schema not found: {schema_path}")
            with target_path.open() as fh:
                instance = yaml.safe_load(fh)
            with schema_path.open() as fh:
                schema = json.load(fh)
            try:
                jsonschema.validate(instance, schema)
                return ConditionResult(cid, True, f"valid against {schema_path.name}")
            except jsonschema.ValidationError as e:
                return ConditionResult(cid, False, f"schema violation: {e.message}")

        if ctype == "command":
            cmd_str = condition.get("command", "")
            result = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=condition.get("timeout_s", 30),
                cwd=str(repo_root),
            )
            ok = result.returncode == 0
            observed = (result.stdout.strip() or result.stderr.strip() or f"exit {result.returncode}")[:200]
            return ConditionResult(cid, ok, observed)

        if ctype == "http":
            import ssl
            import urllib.error
            import urllib.request
            url = condition.get("url", "")
            expect = condition.get("expect_status", 200)
            timeout = condition.get("timeout_s", 10)
            # Don't follow redirects — the check is for the status code itself
            # (e.g. 308 redirect). Also disable cert verification so self-signed
            # certs used during bootstrap don't cause false failures.
            ctx_ssl = ssl.create_default_context()
            ctx_ssl.check_hostname = False
            ctx_ssl.verify_mode = ssl.CERT_NONE

            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx_ssl))
            try:
                with opener.open(url, timeout=timeout) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception as exc:
                return ConditionResult(cid, False, f"http error: {exc}")
            ok = code == expect
            return ConditionResult(cid, ok, f"HTTP {code} (expected {expect})")

        if ctype == "tls":
            import datetime
            import socket
            import ssl
            host = condition.get("host", "")
            port = condition.get("port", 443)
            expect_days = condition.get("expect_days_remaining", 0)
            timeout = condition.get("timeout_s", 10)
            try:
                ctx_ssl = ssl.create_default_context()
                ctx_ssl.check_hostname = False
                ctx_ssl.verify_mode = ssl.CERT_NONE
                with socket.create_connection((host, port), timeout=timeout) as raw:
                    with ctx_ssl.wrap_socket(raw, server_hostname=host) as s:
                        cert = s.getpeercert()
                if not cert:
                    return ConditionResult(cid, False, "tls: no certificate presented")
                not_after = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (not_after - datetime.datetime.utcnow()).days
                ok = days_left >= expect_days
                return ConditionResult(cid, ok, f"cert expires in {days_left}d (need ≥{expect_days}d)")
            except Exception as exc:
                return ConditionResult(cid, False, f"tls error: {exc}")

        if ctype == "tcp":
            import socket
            host = condition.get("host", "")
            port = int(condition.get("port", 80))
            timeout = condition.get("timeout_s", 5)
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    pass
                return ConditionResult(cid, True, f"tcp:{host}:{port} reachable")
            except Exception as exc:
                return ConditionResult(cid, False, f"tcp:{host}:{port} unreachable: {exc}")

        return ConditionResult(cid, False, f"unknown condition type: {ctype!r}")

    except Exception as exc:  # noqa: BLE001
        return ConditionResult(cid, False, f"exception: {exc}", error=str(exc))


def step_status(result: StepResult) -> str:
    """Return a human-readable one-line status for a step result.

    Pure function — no IO. Tested directly.
    """
    if result.status == "skipped":
        return f"[SKIP] {result.step_id}"
    if result.status == "passed":
        return f"[PASS] {result.step_id}  ({result.duration_s:.1f}s, {result.retries_used} retries)"
    failed_pre = result.failed_preconditions()
    failed_post = result.failed_postconditions()
    if failed_pre:
        return f"[FAIL] {result.step_id}  precondition: {failed_pre[0].condition_id}: {failed_pre[0].observed}"
    if failed_post:
        return f"[FAIL] {result.step_id}  postcondition: {failed_post[0].condition_id}: {failed_post[0].observed}"
    return f"[ERR ] {result.step_id}  {result.error or 'unknown error'}"


# --------------------------------------------------------------------------- #
# Step executor
# --------------------------------------------------------------------------- #


def _run_make(
    target: str,
    *,
    repo_root: Path = REPO_ROOT,
    timeout: int = 1800,
    extra_vars: list[str] | None = None,
) -> tuple[int, str, str]:
    """Run `make <target>` and return (rc, stdout, stderr)."""
    import os

    cmd = ["make", target]
    for ev in extra_vars or []:
        cmd.append(ev)
    env = dict(os.environ)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
            env=env,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"make {target} timed out after {timeout}s"
    except FileNotFoundError:
        return 127, "", "make: command not found"


def _resolve_condition(
    raw: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """If raw has post_condition_ref, merge the catalog entry (raw overrides catalog)."""
    ref = raw.get("post_condition_ref")
    if ref and ref in catalog:
        merged = {**catalog[ref], **raw}
        merged.pop("post_condition_ref", None)
        return merged
    return raw


def run_step(
    step: dict[str, Any],
    *,
    ctx: dict[str, str],
    max_retries: int = 0,
    timeout_s: int = 1800,
    dry_run: bool = False,
    repo_root: Path = REPO_ROOT,
    post_conditions_catalog: dict[str, dict[str, Any]] | None = None,
) -> StepResult:
    """Execute one step: check preconditions, run make target, check postconditions.

    Not a pure function (spawns subprocesses). Extracted for testability.
    """
    step_id = step["id"]
    make_target = step.get("make_target", step_id)
    retries = step.get("retries", max_retries)
    timeout = step.get("timeout_s", timeout_s)

    result = StepResult(step_id=step_id, make_target=make_target, status="error")
    catalog = post_conditions_catalog or {}

    # Evaluate preconditions.
    for raw_cond in step.get("preconditions") or []:
        resolved = _resolve_condition(raw_cond, catalog)
        cond = expand_templates(ctx, resolved)
        cr = evaluate_condition(cond, repo_root=repo_root)
        result.precondition_results.append(cr)
    if result.failed_preconditions():
        result.status = "failed"
        return result

    if dry_run:
        result.status = "passed"
        result.make_stdout = f"[dry-run] would run: make {make_target}"
        return result

    # Run make target with retries.
    t0 = time.monotonic()
    attempt = 0
    rc, stdout, stderr = 0, "", ""
    while attempt <= retries:
        rc, stdout, stderr = _run_make(
            make_target,
            repo_root=repo_root,
            timeout=timeout,
        )
        if rc == 0:
            break
        attempt += 1
        if attempt <= retries:
            time.sleep(min(10 * attempt, 60))
    result.make_exit_code = rc
    result.make_stdout = stdout[-4000:] if len(stdout) > 4000 else stdout
    result.make_stderr = stderr[-4000:] if len(stderr) > 4000 else stderr
    result.retries_used = attempt
    result.duration_s = time.monotonic() - t0

    if rc != 0:
        result.status = "failed"
        result.error = f"make {make_target} exited {rc}"
        return result

    # Evaluate postconditions.
    # A condition with critical: false is recorded but does not fail the step.
    # This allows steps whose TLS/HTTP checks are deferred (e.g. cert not yet
    # issued) to still be marked passed so the bootstrap chain continues.
    critical_failure = False
    for raw_cond in step.get("postconditions") or []:
        resolved = _resolve_condition(raw_cond, catalog)
        cond = expand_templates(ctx, resolved)
        cr = evaluate_condition(cond, repo_root=repo_root)
        result.postcondition_results.append(cr)
        if not cr.ok and cond.get("critical", True):
            critical_failure = True
    if critical_failure:
        result.status = "failed"
    else:
        result.status = "passed"
    return result


# --------------------------------------------------------------------------- #
# Receipt I/O
# --------------------------------------------------------------------------- #


def _write_receipt(receipt: BootstrapReceipt, *, receipts_dir: Path = RECEIPTS_DIR) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = "receipt" if receipt.outcome == "success" else f"{receipt.failed_step_id or 'unknown'}-failure"
    out = receipts_dir / f"{ts}-bootstrap-{suffix}.json"
    out.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n")
    return out


def load_last_failure_receipt(*, receipts_dir: Path = RECEIPTS_DIR) -> dict[str, Any] | None:
    """Return the most recent failure receipt, or None.

    Pure-ish (reads files, no side effects). Used by --resume-from auto-detect.
    """
    if not receipts_dir.is_dir():
        return None
    candidates = sorted(receipts_dir.glob("*-bootstrap-*-failure.json"), reverse=True)
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text())
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Main orchestration loop
# --------------------------------------------------------------------------- #


def orchestrate(
    steps: list[dict[str, Any]],
    deployment: str,
    *,
    ctx: dict[str, str],
    gates: dict[str, Any],
    resume_from: str | None = None,
    dry_run: bool = False,
    repo_root: Path = REPO_ROOT,
    write_receipt: bool = True,
    receipts_dir: Path = RECEIPTS_DIR,
    _stderr=sys.stderr,
) -> BootstrapReceipt:
    """Drive the bootstrap chain and return a BootstrapReceipt.

    The return value (not exit code) is the authoritative result. Callers decide
    whether to exit non-zero based on `receipt.outcome`.
    """
    fail_fast: bool = gates.get("fail_fast", True)
    max_retries: int = gates.get("max_retries_per_step", 0)
    step_timeout_s: int = gates.get("step_timeout_s", 1800)

    now = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt = BootstrapReceipt(
        schema_version=1,
        receipt_id=now,
        deployment=deployment,
        ran_at=now,
        outcome="partial",
        steps_attempted=0,
        steps_passed=0,
        steps_failed=0,
        steps_skipped=0,
        resume_from=resume_from,
    )

    post_conditions_catalog = _load_post_conditions()
    steps_to_run = select_steps(steps, resume_from=resume_from)
    skipped_count = len(steps) - len(steps_to_run)
    receipt.steps_skipped = skipped_count

    _stderr.write(f"bootstrap-orchestrator: deployment={deployment!r} steps={len(steps_to_run)} skip={skipped_count}\n")
    if dry_run:
        _stderr.write("  [DRY-RUN] make targets will not be invoked\n")

    stop = False
    for step in steps_to_run:
        if stop:
            # Remaining steps not attempted due to fail_fast.
            skipped = StepResult(
                step_id=step["id"],
                make_target=step.get("make_target", step["id"]),
                status="skipped",
            )
            receipt.step_results.append(skipped)
            receipt.steps_skipped += 1
            continue

        _stderr.write(f"  step {step['id']}: {step.get('title', '')}\n")
        sr = run_step(
            step,
            ctx=ctx,
            max_retries=max_retries,
            timeout_s=step_timeout_s,
            dry_run=dry_run,
            repo_root=repo_root,
            post_conditions_catalog=post_conditions_catalog,
        )
        receipt.step_results.append(sr)
        receipt.steps_attempted += 1
        _stderr.write(f"    {step_status(sr)}\n")

        if sr.status == "passed":
            receipt.steps_passed += 1
        else:
            receipt.steps_failed += 1
            receipt.failed_step_id = step["id"]
            if fail_fast:
                stop = True

    receipt.outcome = "success" if receipt.steps_failed == 0 else "failure"

    if write_receipt:
        out = _write_receipt(receipt, receipts_dir=receipts_dir)
        try:
            display = out.relative_to(repo_root)
        except ValueError:
            display = out
        _stderr.write(f"  receipt: {display}\n")

    return receipt


# --------------------------------------------------------------------------- #
# Status reporter (pure)
# --------------------------------------------------------------------------- #


def format_status(receipt: dict[str, Any]) -> str:
    """Return a human-readable status string from a receipt dict.

    Pure function — no IO. Tested directly.
    """
    lines = [
        f"Bootstrap status for {receipt.get('deployment', '?')}",
        f"  outcome:  {receipt.get('outcome', '?')}",
        f"  ran_at:   {receipt.get('ran_at', '?')}",
        f"  passed:   {receipt.get('steps_passed', 0)}",
        f"  failed:   {receipt.get('steps_failed', 0)}",
        f"  skipped:  {receipt.get('steps_skipped', 0)}",
    ]
    if receipt.get("failed_step_id"):
        lines.append(f"  failed at: {receipt['failed_step_id']}")
    for sr in receipt.get("step_results") or []:
        icon = {"passed": "✓", "failed": "✗", "skipped": "–", "error": "!"}.get(sr.get("status", ""), "?")
        lines.append(f"  {icon} {sr.get('step_id', '?')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _load_steps() -> list[dict[str, Any]]:
    if not STEPS_PATH.is_file():
        sys.exit(f"bootstrap_steps.yml not found: {STEPS_PATH}")
    with STEPS_PATH.open() as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("steps") or []


def _load_post_conditions() -> dict[str, dict[str, Any]]:
    """Load config/post_conditions.yml and return a dict keyed by condition id."""
    if not POST_CONDITIONS_PATH.is_file():
        return {}
    try:
        with POST_CONDITIONS_PATH.open() as fh:
            data = yaml.safe_load(fh) or {}
        catalog = {}
        for cond in data.get("conditions") or data.get("post_conditions") or []:
            if "id" in cond:
                catalog[cond["id"]] = cond
        return catalog
    except Exception:  # noqa: BLE001
        return {}


def _load_gates() -> dict[str, Any]:
    """Load gates config from `.local/manifest.yml`, if present."""
    if MANIFEST_PATH.is_file():
        try:
            with MANIFEST_PATH.open() as fh:
                manifest = yaml.safe_load(fh) or {}
            return manifest.get("gates") or {}
        except Exception:  # noqa: BLE001
            pass
    return {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resume-from", dest="resume_from", help="Step id to resume from (skip earlier steps)")
    p.add_argument(
        "--resume-last", action="store_true", help="Resume from the last failed step (reads last failure receipt)"
    )
    p.add_argument("--status", action="store_true", help="Print status from last receipt and exit")
    p.add_argument("--dry-run", action="store_true", help="Print steps without invoking make targets")
    p.add_argument("--no-receipt", action="store_true", help="Do not write receipt files")
    p.add_argument("--json", action="store_true", help="Emit receipt JSON to stdout on completion")
    args = p.parse_args(argv)

    identity = _load_identity()
    deployment_name = identity.get("platform_domain") or "unknown"

    # --status: print last receipt and exit.
    if args.status:
        receipt = load_last_failure_receipt()
        if receipt is None:
            if RECEIPTS_DIR.is_dir():
                candidates = sorted(RECEIPTS_DIR.glob("*-bootstrap-receipt.json"), reverse=True)
                if candidates:
                    receipt = json.loads(candidates[0].read_text())
        if receipt is None:
            sys.stderr.write("No bootstrap receipt found.\n")
            return 2
        sys.stderr.write(format_status(receipt) + "\n")
        if args.json:
            json.dump(receipt, sys.stdout, indent=2)
            sys.stdout.write("\n")
        return 0 if receipt.get("outcome") == "success" else 1

    steps = _load_steps()
    gates = _load_gates()

    # --resume-last: find the failed step from last receipt.
    resume_from = args.resume_from
    if args.resume_last and resume_from is None:
        last = load_last_failure_receipt()
        if last and last.get("failed_step_id"):
            resume_from = last["failed_step_id"]
            sys.stderr.write(f"bootstrap-orchestrator: resuming from last failure at {resume_from!r}\n")
        else:
            sys.stderr.write("bootstrap-orchestrator: no prior failure receipt found; starting from step 0\n")

    manifest_for_ctx: dict[str, Any] = {}
    if MANIFEST_PATH.is_file():
        try:
            with MANIFEST_PATH.open() as fh:
                manifest_for_ctx = yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001
            manifest_for_ctx = {}
    ctx = build_template_ctx(identity, manifest_for_ctx)

    receipt = orchestrate(
        steps,
        deployment_name,
        ctx=ctx,
        gates=gates,
        resume_from=resume_from,
        dry_run=args.dry_run,
        write_receipt=not args.no_receipt,
    )

    if args.json:
        json.dump(receipt.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")

    summary = f"bootstrap: {receipt.outcome} — {receipt.steps_passed} passed, {receipt.steps_failed} failed, {receipt.steps_skipped} skipped\n"
    sys.stderr.write(summary)

    return 0 if receipt.outcome == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
