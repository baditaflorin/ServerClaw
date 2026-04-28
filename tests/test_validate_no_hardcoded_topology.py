"""Unit tests for the late_bound_default rule in validate_no_hardcoded_topology.py
— ADR 0444 item 20.

The audit category from ADR 0438 ("openbao_postgres_host defaulting to a
production IP before overlay applied") is the canonical case the rule
guards. These tests exercise the rule directly against synthetic role
defaults — no live repo scan, no inventory.

The strong/heuristic rules are covered by tests/test_adr_0443_topology_drift.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_no_hardcoded_topology.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("vnht", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["vnht"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vnht():
    return _load_module()


@pytest.fixture
def role_default_path(tmp_path):
    """Return a path that LATE_BOUND_TARGET_GLOBS will recognise.

    The rule scans `roles/*/defaults/main.yml` (and the collections mirror).
    The match is glob-based on the relative path, so the fixture creates a
    role-shaped tree under tmp_path.
    """

    def _mk(content: str) -> tuple[Path, Path]:
        role_dir = tmp_path / "roles" / "demo" / "defaults"
        role_dir.mkdir(parents=True)
        path = role_dir / "main.yml"
        path.write_text(content, encoding="utf-8")
        rel = path.relative_to(tmp_path)
        return path, rel

    return _mk


def test_late_bound_default_flags_known_prod_ip(vnht, role_default_path):
    path, rel = role_default_path("openbao_postgres_host: \"{{ openbao_postgres_host | default('10.10.10.60') }}\"\n")
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == "late_bound_default"
    assert f.matched == "10.10.10.60"
    assert f.line == 1
    assert "before any deployment overlay" in f.detail


def test_late_bound_default_ignores_unknown_ip(vnht, role_default_path):
    """An IP that is not in known_ips must not be flagged. The rule is
    explicitly bounded to the topology we know — random literals are
    out of scope."""
    path, rel = role_default_path("some_var: \"{{ some_var | default('192.0.2.1') }}\"\n")
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert findings == []


def test_late_bound_default_double_quotes_match(vnht, role_default_path):
    path, rel = role_default_path('host: "{{ host | default("10.10.10.60") }}"\n')
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert len(findings) == 1
    assert findings[0].matched == "10.10.10.60"


def test_late_bound_default_allow_marker_suppresses(vnht, role_default_path):
    """The `# late-bound-allow:` marker on the same line must suppress."""
    path, rel = role_default_path(
        "host: \"{{ host | default('10.10.10.60') }}\"  # late-bound-allow: required for first-boot bootstrap\n"
    )
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert findings == []


def test_late_bound_default_existing_noqa_marker_also_suppresses(vnht, role_default_path):
    """Backwards compat — the older `noqa: topology-hardcode` marker is
    honoured for the new rule too, since callers may have existing
    annotations."""
    path, rel = role_default_path("host: \"{{ host | default('10.10.10.60') }}\"  # noqa: topology-hardcode\n")
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert findings == []


def test_late_bound_default_ignores_files_outside_target_globs(vnht, tmp_path):
    """A literal in a template file (`*.j2`) or task file is NOT a
    role default — those are out of scope for this rule. They run
    through the strong/heuristic rules instead."""
    path = tmp_path / "roles" / "demo" / "tasks" / "main.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "- name: example\n  set_fact:\n    x: \"{{ x | default('10.10.10.60') }}\"\n",
        encoding="utf-8",
    )
    rel = path.relative_to(tmp_path)
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert findings == []


def test_late_bound_default_handles_collections_mirror(vnht, tmp_path):
    """The rule must also fire on the collections-mirror role tree."""
    role_dir = tmp_path / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "demo" / "defaults"
    role_dir.mkdir(parents=True)
    path = role_dir / "main.yml"
    path.write_text("host: \"{{ host | default('10.10.10.60') }}\"\n", encoding="utf-8")
    rel = path.relative_to(tmp_path)
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    assert len(findings) == 1
    assert findings[0].matched == "10.10.10.60"


def test_late_bound_default_multiple_hits_per_file(vnht, role_default_path):
    path, rel = role_default_path(
        "a: \"{{ a | default('10.10.10.60') }}\"\n"
        "b: \"{{ b | default('10.10.10.92') }}\"\n"
        "c: \"{{ c | default('192.0.2.99') }}\"\n"  # not in known_ips
    )
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60", "10.10.10.92"}))
    assert len(findings) == 2
    assert {f.matched for f in findings} == {"10.10.10.60", "10.10.10.92"}
    assert {f.line for f in findings} == {1, 2}


def test_late_bound_default_empty_known_ips_short_circuits(vnht, role_default_path):
    """When the validator is invoked with no known IPs (e.g. the host
    fixture is missing), the rule must short-circuit cleanly rather
    than emitting noisy false positives or crashing."""
    path, rel = role_default_path("host: \"{{ host | default('10.10.10.60') }}\"\n")
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset())
    assert findings == []


def test_late_bound_default_negative_lookahead_avoids_substring_ips(vnht, role_default_path):
    """`10.10.10.60` must not match if the literal is `10.10.10.600`
    (impossible IP, but a regex that lacks a boundary would still hit)."""
    path, rel = role_default_path("host: \"{{ host | default('10.10.10.600') }}\"\n")
    findings = vnht.scan_late_bound_defaults(path, rel, frozenset({"10.10.10.60"}))
    # The current regex does not enforce IP-boundary; if a future change
    # adds `10.10.10.600` as a known IP it would match. Today, with
    # `10.10.10.60` as the only known IP, `10.10.10.600` is not a match
    # because the regex literal is `10\.10\.10\.60` and the pattern
    # `default('10\\.10\\.10\\.60')` does not match the string
    # `default('10.10.10.600')` due to the closing quote.
    assert findings == []
