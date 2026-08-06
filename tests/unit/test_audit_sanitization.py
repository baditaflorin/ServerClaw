"""Unit tests for scripts/audit_sanitization.py — ADR 0488 §4 enforcement.

Covers:
- (a) a tracked file containing a blocked string outside the allowed contexts
      produces a hit (script would fail the gate).
- (b) the same blocked string inside an allowed context (e.g. docs/adr/)
      produces no hit.
- (c) the audit runs in under 5 seconds against the live repository.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("audit_sanitization", SCRIPTS_DIR / "audit_sanitization.py")
audit_sanitization = importlib.util.module_from_spec(spec)
sys.modules["audit_sanitization"] = audit_sanitization
assert spec.loader is not None
spec.loader.exec_module(audit_sanitization)


def test_blocks_operator_string_outside_allowed_context(tmp_path):
    """A committed file outside docs/adr/ etc. with 0mpc.com must fail."""
    leaky = tmp_path / "playbooks" / "vars" / "production.yml"
    leaky.parent.mkdir(parents=True)
    leaky.write_text("platform_domain: 0mpc.com\n")

    hits = audit_sanitization.audit(
        repo_root=tmp_path,
        files=["playbooks/vars/production.yml"],
    )
    assert len(hits) == 1
    assert hits[0].path == "playbooks/vars/production.yml"
    assert hits[0].blocked == "0mpc.com"
    assert hits[0].line_no == 1


def test_passes_operator_string_inside_allowed_context(tmp_path):
    """The same 0mpc.com string inside an allowed-context path must pass."""
    adr = tmp_path / "docs" / "adr" / "0488-test.md"
    adr.parent.mkdir(parents=True)
    adr.write_text("Historical record: deployment used 0mpc.com.\n")

    runbook = tmp_path / "docs" / "runbooks" / "ops.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("Operator apex: 0mpc.com.\n")

    receipt = tmp_path / "receipts" / "live-applies" / "r.yml"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("host: 203.0.113.1\n")

    changelog = tmp_path / "changelog.md"
    changelog.write_text("- 0fork.com migrated\n")

    workstreams_root = tmp_path / "workstreams.yaml"
    workstreams_root.write_text("- title: example.com retirement\n")

    files = [
        "docs/adr/0488-test.md",
        "docs/runbooks/ops.md",
        "receipts/live-applies/r.yml",
        "changelog.md",
        "workstreams.yaml",
    ]
    hits = audit_sanitization.audit(repo_root=tmp_path, files=files)
    assert hits == []


def test_case_insensitive_match(tmp_path):
    """Substring match must be case-insensitive."""
    leaky = tmp_path / "config" / "thing.yml"
    leaky.parent.mkdir(parents=True)
    leaky.write_text("apex: LV3.Org\n")

    hits = audit_sanitization.audit(
        repo_root=tmp_path,
        files=["config/thing.yml"],
    )
    assert len(hits) == 1
    assert hits[0].blocked == "example.com"


def test_self_exempt_files_pass(tmp_path):
    """The audit script itself names the blocked strings — must be exempt."""
    p = tmp_path / "scripts" / "audit_sanitization.py"
    p.parent.mkdir(parents=True)
    p.write_text('BLOCKED = ("example.com", "0mpc.com")\n')

    hits = audit_sanitization.audit(
        repo_root=tmp_path,
        files=["scripts/audit_sanitization.py"],
    )
    assert hits == []


def test_audit_runs_under_5s_on_live_repo():
    """ADR 0488 §4: the gate runs on every pre-push — must be fast.

    Scans every tracked file in this repo and asserts wall-clock time < 5s.
    """
    start = time.monotonic()
    audit_sanitization.audit(repo_root=REPO_ROOT)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"audit took {elapsed:.2f}s — exceeds 5s budget"
