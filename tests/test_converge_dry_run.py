"""Unit tests for scripts/converge_dry_run.py — ADR 0444 item 10.

Covers the helper functions directly (changed-role detection, playbook
discovery, fixture selection, matrix formatting). The actual ansible
shell-out is not exercised here because it requires ansible-playbook on
PATH and a connectable inventory; the gate runs that integration check
separately.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "converge_dry_run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("converge_dry_run", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec_module so @dataclass can resolve its module
    # via sys.modules during class construction.
    sys.modules["converge_dry_run"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cdr():
    return _load_module()


# ---------------------------------------------------------------------------
# _extract_role_names
# ---------------------------------------------------------------------------


def test_extract_role_names_handles_both_role_trees(cdr):
    files = [
        "roles/keycloak_runtime/defaults/main.yml",
        "collections/ansible_collections/lv3/platform/roles/openbao_postgres_backend/tasks/main.yml",
        "roles/_template/service_scaffold/defaults-main.yml.tpl",  # excluded
        "docs/adr/0445-phase1-multi-deployment-hardening.md",  # excluded
        "playbooks/keycloak.yml",  # excluded
    ]
    assert cdr._extract_role_names(files) == [
        "keycloak_runtime",
        "openbao_postgres_backend",
    ]


def test_extract_role_names_dedupes_across_trees(cdr):
    """A role that exists under both `roles/` and `collections/.../roles/`
    must appear once in the changed-role list, not twice."""
    files = [
        "roles/keycloak_runtime/defaults/main.yml",
        "collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml",
    ]
    assert cdr._extract_role_names(files) == ["keycloak_runtime"]


def test_extract_role_names_empty_input(cdr):
    assert cdr._extract_role_names([]) == []


def test_extract_role_names_skips_blank_and_comments(cdr):
    files = ["", "  ", "# a comment", "roles/foo/defaults/main.yml"]
    assert cdr._extract_role_names(files) == ["foo"]


# ---------------------------------------------------------------------------
# _roles_referenced
# ---------------------------------------------------------------------------


def test_roles_referenced_matches_fq_and_short_forms(cdr):
    text = """
- name: example
  hosts: all
  roles:
    - role: lv3.platform.keycloak_runtime
      tags: [auth]
    - role: openbao_postgres_backend
    - lv3.platform.api_gateway_runtime
"""
    refs = cdr._roles_referenced(text)
    assert refs == {
        "keycloak_runtime",
        "openbao_postgres_backend",
        "api_gateway_runtime",
    }, f"unexpected refs: {refs}"


def test_roles_referenced_ignores_name_keys(cdr):
    """`- name: foo` is a play name, not a role reference. The matcher
    must not flag it as a role."""
    text = """
- name: example play
  hosts: all
  roles:
    - role: keycloak_runtime
"""
    refs = cdr._roles_referenced(text)
    assert "name" not in refs
    assert "example" not in refs
    assert refs == {"keycloak_runtime"}


# ---------------------------------------------------------------------------
# discover_fixtures
# ---------------------------------------------------------------------------


def test_discover_fixtures_all_returns_committed_set(cdr):
    fixtures = cdr.discover_fixtures("all")
    names = sorted(p.name for p in fixtures)
    assert names == ["0fork-shape.yml", "lv3-shape.yml", "synthetic-shape.yml"], (
        f"discover_fixtures('all') returned unexpected set: {names}"
    )


def test_discover_fixtures_selector_picks_subset(cdr):
    fixtures = cdr.discover_fixtures("lv3,0fork")
    names = sorted(p.name for p in fixtures)
    assert names == ["0fork-shape.yml", "lv3-shape.yml"]


def test_discover_fixtures_unknown_stem_raises(cdr):
    with pytest.raises(RuntimeError, match="unknown fixture"):
        cdr.discover_fixtures("nope")


# ---------------------------------------------------------------------------
# Matrix formatting
# ---------------------------------------------------------------------------


def test_format_matrix_groups_by_role(cdr):
    results = [
        cdr.CellResult("alpha", "lv3-shape.yml", "playbooks/alpha.yml", True, "ok"),
        cdr.CellResult("alpha", "0fork-shape.yml", "playbooks/alpha.yml", False, "boom"),
        cdr.CellResult("beta", "lv3-shape.yml", "playbooks/beta.yml", True, "ok"),
    ]
    formatted = cdr._format_matrix(results)
    assert "[PASS] alpha" in formatted
    assert "[FAIL] alpha" in formatted
    assert "boom" in formatted
    assert "[PASS] beta" in formatted
    # alpha lines should appear before beta lines (sorted by role)
    assert formatted.index("alpha") < formatted.index("beta")


def test_format_matrix_empty(cdr):
    assert cdr._format_matrix([]) == "(no cells executed)"


# ---------------------------------------------------------------------------
# CLI smoke — no changed roles short-circuits to exit 0
# ---------------------------------------------------------------------------


def test_main_no_changed_roles_exits_zero(cdr, monkeypatch, capsys):
    monkeypatch.setattr(cdr, "detect_changed_roles", lambda base, head="HEAD": [])
    rc = cdr.main(["--base", "origin/main"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no changed roles detected" in out


def test_main_advisory_swallows_failures(cdr, monkeypatch, capsys):
    """--advisory must exit 0 even when cells fail. This is the wiring
    we use for pre-push initially; phase 5 promotes to required."""
    monkeypatch.setattr(cdr, "detect_changed_roles", lambda base, head="HEAD": ["fake_role"])
    monkeypatch.setattr(cdr, "find_playbooks_for_role", lambda role: [])
    # Pretend ansible-playbook is on PATH so we don't short-circuit on the
    # which() check.
    monkeypatch.setattr(cdr.shutil, "which", lambda name: "/usr/bin/ansible-playbook")
    rc = cdr.main(["--base", "origin/main", "--advisory"])
    assert rc == 0  # advisory mode swallows the "no playbook" failure
    out = capsys.readouterr().out
    assert "no playbook references this role" in out
