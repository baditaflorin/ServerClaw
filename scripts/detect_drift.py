"""Drift detector — ADR 0485 §3.

Runs an Ansible playbook in `--check` mode, parses the PLAY RECAP to count
changed tasks, and exits non-zero when changed > 0 (drift detected).

The idea: if `make converge-X` is strictly idempotent (ADR 0485), then any
non-zero `changed` count on a `--check` run means something modified state
between the last converge and now. That modification is drift.

Usage:

    # Detect drift in a single playbook:
    uv run --with pyyaml python scripts/detect_drift.py \\
        --playbook playbooks/harbor.yml

    # Pass extra-vars the way the Makefile does:
    uv run ... python scripts/detect_drift.py \\
        --playbook playbooks/harbor.yml \\
        --extra-vars "env=production"

    # Write the drift report:
    uv run ... python scripts/detect_drift.py \\
        --playbook playbooks/harbor.yml \\
        --write-report

Exit codes:
  0  no drift (changed == 0 on every play, no failures)
  1  drift detected (changed > 0) or failures/unreachable > 0
  2  could not resolve deployment or failed to run ansible-playbook

Pure helpers (parse_play_recap, summarise_recap) are tested directly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import REPO_ROOT, load as load_deployment, resolve_active_slug  # noqa: E402

# Paths relative to repo root.
_DEFAULT_INVENTORY = REPO_ROOT / "inventory" / "hosts.yml"
_DEFAULT_KEY = REPO_ROOT / ".local" / "ssh" / "bootstrap.id_ed25519"
_RECEIPTS_DIR = REPO_ROOT / "receipts" / "drift"


# --------------------------------------------------------------------------- #
# Pure helpers (tested directly)
# --------------------------------------------------------------------------- #

# Matches lines like:
#   localhost : ok=14 changed=2 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0
_RECAP_RE = re.compile(
    r"^(?P<host>\S+)\s*:\s*"
    r"ok=(?P<ok>\d+)\s+"
    r"changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+"
    r"failed=(?P<failed>\d+)",
    re.MULTILINE,
)


@dataclass
class HostRecap:
    host: str
    ok: int
    changed: int
    unreachable: int
    failed: int


@dataclass
class DriftReport:
    playbook: str
    deployment: str
    ran_at: str
    ansible_exit_code: int
    hosts: list[HostRecap] = field(default_factory=list)
    drift: bool = False
    total_changed: int = 0
    total_unreachable: int = 0
    total_failed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook": self.playbook,
            "deployment": self.deployment,
            "ran_at": self.ran_at,
            "ansible_exit_code": self.ansible_exit_code,
            "drift": self.drift,
            "total_changed": self.total_changed,
            "total_unreachable": self.total_unreachable,
            "total_failed": self.total_failed,
            "hosts": [asdict(h) for h in self.hosts],
            "error": self.error,
        }


def parse_play_recap(output: str) -> list[HostRecap]:
    """Extract per-host stats from Ansible PLAY RECAP output.

    Pure function — no IO. Tested directly.
    """
    results: list[HostRecap] = []
    for m in _RECAP_RE.finditer(output):
        results.append(
            HostRecap(
                host=m.group("host"),
                ok=int(m.group("ok")),
                changed=int(m.group("changed")),
                unreachable=int(m.group("unreachable")),
                failed=int(m.group("failed")),
            )
        )
    return results


def summarise_recap(hosts: list[HostRecap]) -> tuple[int, int, int]:
    """Return (total_changed, total_unreachable, total_failed) across all hosts.

    Pure function — no IO. Tested directly.
    """
    changed = sum(h.changed for h in hosts)
    unreachable = sum(h.unreachable for h in hosts)
    failed = sum(h.failed for h in hosts)
    return changed, unreachable, failed


def is_drift(hosts: list[HostRecap]) -> bool:
    """Return True if any host reported changed > 0, failures, or unreachable.

    Pure function — no IO. Tested directly.
    """
    changed, unreachable, failed = summarise_recap(hosts)
    return changed > 0 or unreachable > 0 or failed > 0


# --------------------------------------------------------------------------- #
# Ansible runner
# --------------------------------------------------------------------------- #


def _find_bootstrap_key(slug: str) -> Path:
    """Locate the bootstrap SSH key for a deployment."""
    from deployment import DEPLOYMENTS_DIR

    base = DEPLOYMENTS_DIR / slug
    conn_file = base / "connection.yml"
    if conn_file.is_file():
        with conn_file.open() as fh:
            conn = yaml.safe_load(fh) or {}
        key_raw = (conn.get("proxmox_host") or {}).get("key", "")
        if isinstance(key_raw, str) and key_raw:
            candidate = REPO_ROOT / ".local" / "ssh" / Path(key_raw).name
            if candidate.is_file():
                return candidate
    # Fall back to the standard bootstrap key.
    return _DEFAULT_KEY


def run_playbook_check(
    playbook: Path,
    *,
    slug: str,
    inventory: Path = _DEFAULT_INVENTORY,
    extra_vars: list[str] | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """Run `ansible-playbook --check` and return (exit_code, stdout, stderr).

    Not a pure function (spawns a subprocess). Extracted for testability.
    """
    key = _find_bootstrap_key(slug)
    cmd = [
        "ansible-playbook",
        "--check",
        "-i",
        str(inventory),
        "--private-key",
        str(key),
        "ANSIBLE_HOST_KEY_CHECKING=False",
        str(playbook),
    ]
    # ANSIBLE_HOST_KEY_CHECKING via env, not as arg
    cmd = [
        "ansible-playbook",
        "--check",
        "-i",
        str(inventory),
        "--private-key",
        str(key),
        str(playbook),
    ]
    for ev in extra_vars or []:
        cmd += ["-e", ev]

    env_extras = {"ANSIBLE_HOST_KEY_CHECKING": "False"}
    import os

    env = {**os.environ, **env_extras}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(REPO_ROOT),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"ansible-playbook --check timed out after {timeout}s"
    except FileNotFoundError:
        return 127, "", "ansible-playbook: command not found — is Ansible installed?"


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _write_report(report: DriftReport) -> Path:
    _RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    playbook_slug = Path(report.playbook).stem.replace("/", "-")
    out = _RECEIPTS_DIR / f"{timestamp}-{report.deployment}-{playbook_slug}-drift.json"
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--playbook", required=True, help="Path to the Ansible playbook to check for drift")
    p.add_argument("--slug", help="Deployment slug (defaults to active deployment)")
    p.add_argument(
        "--extra-vars",
        dest="extra_vars",
        action="append",
        default=[],
        help="Extra vars to pass to ansible-playbook (repeatable)",
    )
    p.add_argument("--inventory", default=str(_DEFAULT_INVENTORY), help="Inventory path")
    p.add_argument("--timeout", type=int, default=600, help="Ansible timeout in seconds")
    p.add_argument("--write-report", action="store_true", help="Write drift report JSON to receipts/drift/")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout")
    args = p.parse_args(argv)

    try:
        slug = args.slug or resolve_active_slug()
    except Exception as e:
        sys.exit(f"deployment not resolved: {e}")

    playbook = Path(args.playbook)
    if not playbook.is_absolute():
        playbook = REPO_ROOT / playbook
    if not playbook.is_file():
        sys.exit(f"playbook not found: {playbook}")

    now = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = DriftReport(
        playbook=str(args.playbook),
        deployment=slug,
        ran_at=now,
        ansible_exit_code=0,
    )

    sys.stderr.write(f"detect-drift: running {playbook.name} --check for deployment {slug!r}\n")
    rc, stdout, stderr = run_playbook_check(
        playbook,
        slug=slug,
        inventory=Path(args.inventory),
        extra_vars=args.extra_vars,
        timeout=args.timeout,
    )
    report.ansible_exit_code = rc

    if rc == 127:
        report.error = stderr.strip()
        sys.stderr.write(f"  ERROR: {report.error}\n")
        if args.json:
            json.dump(report.to_dict(), sys.stdout, indent=2)
        return 2

    hosts = parse_play_recap(stdout + "\n" + stderr)
    report.hosts = hosts
    changed, unreachable, failed = summarise_recap(hosts)
    report.total_changed = changed
    report.total_unreachable = unreachable
    report.total_failed = failed
    report.drift = is_drift(hosts) or (rc not in (0, 2))  # rc=2 = changed tasks in check mode

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        status = "DRIFT" if report.drift else "CLEAN"
        sys.stderr.write(f"  [{status}] changed={changed} unreachable={unreachable} failed={failed} ansible_rc={rc}\n")
        if report.drift:
            sys.stderr.write("  Drift detected — reconcile with `make converge-*`\n")
        else:
            sys.stderr.write("  No drift detected.\n")

    if args.write_report:
        out = _write_report(report)
        sys.stderr.write(f"  report written: {out}\n")

    return 1 if report.drift else 0


if __name__ == "__main__":
    sys.exit(main())
