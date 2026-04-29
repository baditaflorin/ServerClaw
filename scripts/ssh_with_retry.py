#!/usr/bin/env python3
"""SSH wrapper with exponential backoff + structured failure classification.

ADR 0464 — wraps a single ssh invocation with up to N retries,
exponential backoff, and a classifier that turns the ssh stderr text
into a structured failure type. Successful classification helps the
operator (and the gate-bypass-waiver-catalog) tell `network_partition`
apart from `auth_failure` apart from `banner_timeout` apart from
`unknown`.

Usage (drop-in for `ssh`):

    python3 scripts/ssh_with_retry.py \
        --retries 3 --base-delay 1.0 --max-delay 10.0 \
        --classify-receipts-dir receipts/ssh-failures \
        -- \
        -i ~/.ssh/id_ed25519 ops@10.10.10.92 'uname -n'

After the inner ssh exits, the wrapper:

  - on success → exit 0, no receipt.
  - on failure that retried successfully → exit 0, ONE receipt
    documenting the classified attempts.
  - on terminal failure → exit with ssh's last exit code, ONE
    receipt documenting every attempt.

The wrapper is intentionally NOT a configuration tool — it forwards
all positional args to ssh after `--`. Operators control behavior
with `--retries`, `--base-delay`, `--max-delay`, and the env vars
`LV3_SSH_RETRY_DEFAULT_RETRIES` / `LV3_SSH_RETRY_DEFAULT_BASE_DELAY`.

Failure classes (matched against ssh stderr):

  - `network_partition`   — "No route to host", "Network is unreachable"
  - `auth_failure`        — "Permission denied", "publickey", "password"
  - `banner_timeout`      — "Connection timed out during banner exchange"
  - `connection_refused`  — "Connection refused"
  - `dns_failure`         — "Could not resolve hostname", "Name or service not known"
  - `host_key_mismatch`   — "REMOTE HOST IDENTIFICATION HAS CHANGED"
  - `unknown`             — anything else

Exit codes mirror ssh: the wrapper preserves the inner exit code on
terminal failure, returns 0 on success (even after retries), and
returns 2 on argparse errors.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


FAILURE_CLASSIFIERS: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "host_key_mismatch",
        [re.compile(r"REMOTE HOST IDENTIFICATION HAS CHANGED", re.IGNORECASE)],
    ),
    (
        "auth_failure",
        [
            re.compile(r"Permission denied", re.IGNORECASE),
            re.compile(r"publickey,gssapi-keyex|publickey,password", re.IGNORECASE),
            re.compile(r"Authentication failed", re.IGNORECASE),
        ],
    ),
    (
        "banner_timeout",
        [
            re.compile(r"Connection timed out during banner exchange", re.IGNORECASE),
            re.compile(r"Connection to .* port \d+ timed out", re.IGNORECASE),
        ],
    ),
    (
        "connection_refused",
        [re.compile(r"Connection refused", re.IGNORECASE)],
    ),
    (
        "dns_failure",
        [
            re.compile(r"Could not resolve hostname", re.IGNORECASE),
            re.compile(r"Name or service not known", re.IGNORECASE),
            re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
        ],
    ),
    (
        "network_partition",
        [
            re.compile(r"No route to host", re.IGNORECASE),
            re.compile(r"Network is unreachable", re.IGNORECASE),
        ],
    ),
]


def classify_ssh_stderr(stderr: str) -> str:
    """Match ssh stderr text against known failure patterns."""
    if not stderr:
        return "unknown"
    for label, patterns in FAILURE_CLASSIFIERS:
        for pat in patterns:
            if pat.search(stderr):
                return label
    return "unknown"


def compute_backoff(attempt: int, base_delay: float, max_delay: float, jitter: bool = True) -> float:
    """Exponential backoff with jitter. attempt is 1-indexed."""
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    if jitter:
        delay *= random.uniform(0.5, 1.5)
    return min(delay, max_delay)


def run_one_attempt(ssh_args: list[str], timeout: float | None = None) -> tuple[int, str, str]:
    """Run `ssh <args>` once. Returns (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        ["ssh", *ssh_args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_failure_receipt(
    receipts_dir: Path,
    *,
    target: str,
    attempts: list[dict],
    final_outcome: str,
) -> Path:
    """Write a receipt summarising every retry attempt and the final outcome.

    Atomic write per ADR 0461.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from check_receipt_freshness import write_receipt_atomic

    now = dt.datetime.now(dt.UTC)
    safe_ts = now.strftime("%Y%m%dT%H%M%SZ")
    safe_target = re.sub(r"[^a-zA-Z0-9_.-]+", "_", target)[:64]
    receipt_path = receipts_dir / f"{safe_target}-{safe_ts}.json"
    payload = {
        "schema_version": "1.0.0",
        "target": target,
        "recorded_at": now.isoformat(timespec="seconds"),
        "attempts": attempts,
        "final_outcome": final_outcome,
    }
    write_receipt_atomic(receipt_path, payload)
    return receipt_path


_SSH_VALUE_FLAGS = {"-i", "-p", "-l", "-o", "-F", "-J", "-L", "-R", "-D", "-W", "-c", "-m", "-S", "-Q", "-b", "-B", "-E", "-I"}


def _extract_target(ssh_args: list[str]) -> str:
    """Best-effort: ssh's first non-flag argument is usually `[user@]host`.

    Honors the value-taking single-letter flags (e.g. `-i key`, `-p 22`)
    by skipping their following argument so it doesn't get mistaken for
    the target.
    """
    skip_next = False
    for arg in ssh_args:
        if skip_next:
            skip_next = False
            continue
        if arg in _SSH_VALUE_FLAGS:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ssh_with_retry",
        description=__doc__.split("\n\n")[0],
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(os.environ.get("LV3_SSH_RETRY_DEFAULT_RETRIES", "3")),
        help="Total attempts (1 = no retry).",
    )
    parser.add_argument(
        "--base-delay",
        type=float,
        default=float(os.environ.get("LV3_SSH_RETRY_DEFAULT_BASE_DELAY", "1.0")),
        help="Initial backoff seconds (attempt 1 → no delay; attempt 2 → base, attempt 3 → 2*base, ...).",
    )
    parser.add_argument("--max-delay", type=float, default=10.0)
    parser.add_argument(
        "--classify-receipts-dir",
        type=Path,
        default=None,
        help="Write a receipt here on retry / failure (default: skip).",
    )
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Disable jitter for deterministic backoff (test-only).",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=10.0,
        help="Subprocess timeout per ssh attempt in seconds.",
    )
    parser.add_argument("ssh_args", nargs=argparse.REMAINDER, help="Args after `--` are forwarded to ssh.")
    args = parser.parse_args(argv)

    if args.retries < 1:
        print("ssh_with_retry: --retries must be >= 1", file=sys.stderr)
        return 2

    if args.ssh_args and args.ssh_args[0] == "--":
        ssh_args = args.ssh_args[1:]
    else:
        ssh_args = args.ssh_args

    if not ssh_args:
        parser.print_usage(sys.stderr)
        print("ssh_with_retry: no ssh args. Pass after `--`.", file=sys.stderr)
        return 2

    target = _extract_target(ssh_args)
    attempts: list[dict] = []
    final_rc = 1
    final_stdout = ""
    final_stderr = ""

    for attempt in range(1, args.retries + 1):
        if attempt > 1:
            delay = compute_backoff(attempt - 1, args.base_delay, args.max_delay, jitter=not args.no_jitter)
            time.sleep(delay)
            attempts[-1]["sleep_before_next"] = round(delay, 3)

        try:
            rc, out, err = run_one_attempt(ssh_args, timeout=args.connect_timeout)
        except subprocess.TimeoutExpired:
            rc, out, err = 124, "", "ssh subprocess timed out"
        attempts.append(
            {
                "attempt": attempt,
                "exit_code": rc,
                "classification": classify_ssh_stderr(err),
                "stderr_excerpt": err[:512],
            }
        )

        final_rc, final_stdout, final_stderr = rc, out, err
        if rc == 0:
            break

    # Pass through to caller stdout/stderr.
    if final_stdout:
        sys.stdout.write(final_stdout)
    if final_stderr:
        sys.stderr.write(final_stderr)

    final_outcome = "success" if final_rc == 0 else "terminal_failure"

    # Write a receipt only if (a) we had at least one failed attempt, AND
    # (b) the operator opted in via --classify-receipts-dir.
    failed_attempts = [a for a in attempts if a["exit_code"] != 0]
    if failed_attempts and args.classify_receipts_dir is not None:
        try:
            write_failure_receipt(
                args.classify_receipts_dir,
                target=target,
                attempts=attempts,
                final_outcome=final_outcome,
            )
        except OSError as exc:  # pragma: no cover — logged but not fatal
            print(f"ssh_with_retry: failed to write receipt: {exc}", file=sys.stderr)

    return final_rc


if __name__ == "__main__":
    sys.exit(main())
