"""Unit tests for scripts/refresh_safe_receipts.py — ADR 0449 phase 4.3.

Exercises the classification logic against synthetic role trees and
mocked git output. The live `versions/stack.yaml` is not exercised —
that's integration territory and would couple test outcomes to
whatever happens to be in flight on the day the tests run.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "refresh_safe_receipts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refresh_safe_receipts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["refresh_safe_receipts"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rsr():
    return _load_module()


# ---------------------------------------------------------------------------
# parse_receipt_date
# ---------------------------------------------------------------------------


def test_parse_receipt_date_real_slug(rsr):
    assert rsr.parse_receipt_date("2026-04-21-some-receipt") == dt.date(2026, 4, 21)


def test_parse_receipt_date_rejects_short(rsr):
    assert rsr.parse_receipt_date("2026") is None
    assert rsr.parse_receipt_date("") is None


def test_parse_receipt_date_rejects_invalid_calendar(rsr):
    assert rsr.parse_receipt_date("2026-02-30-bogus") is None


# ---------------------------------------------------------------------------
# candidate_role_paths
# ---------------------------------------------------------------------------


def test_candidate_role_paths_finds_runtime_and_postgres(rsr, tmp_path):
    (tmp_path / "roles" / "keycloak_runtime").mkdir(parents=True)
    (tmp_path / "roles" / "keycloak_postgres").mkdir(parents=True)
    (tmp_path / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "keycloak_runtime").mkdir(
        parents=True
    )
    out = rsr.candidate_role_paths("keycloak", tmp_path)
    assert "roles/keycloak_runtime" in out
    assert "roles/keycloak_postgres" in out
    assert "collections/ansible_collections/lv3/platform/roles/keycloak_runtime" in out


def test_candidate_role_paths_returns_empty_when_unknown(rsr, tmp_path):
    assert rsr.candidate_role_paths("ghost_service", tmp_path) == []


def test_candidate_role_paths_finds_bare_service_name(rsr, tmp_path):
    (tmp_path / "roles" / "monitoring").mkdir(parents=True)
    out = rsr.candidate_role_paths("monitoring", tmp_path)
    assert out == ["roles/monitoring"]


# ---------------------------------------------------------------------------
# Phase 6.1 — registry-driven role lookup
# ---------------------------------------------------------------------------


def _write_registry(tmp_path: Path, services: dict[str, list[str]]) -> Path:
    """Write a synthetic platform_services.yml with the given services."""
    import yaml

    path = tmp_path / "inventory" / "group_vars" / "all" / "platform_services.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"platform_service_registry": {svc: {"roles": roles} for svc, roles in services.items()}}
    path.write_text(yaml.safe_dump(payload))
    return path


def test_load_service_registry_roles_picks_up_explicit_roles(rsr, tmp_path):
    _write_registry(tmp_path, {"alpha": ["alpha_runtime", "alpha_postgres"], "beta": []})
    roles = rsr.load_service_registry_roles(tmp_path)
    assert roles["alpha"] == ["alpha_runtime", "alpha_postgres"]
    assert roles["beta"] == []


def test_load_service_registry_roles_handles_missing_file(rsr, tmp_path):
    assert rsr.load_service_registry_roles(tmp_path) == {}


def test_load_service_registry_roles_handles_malformed_yaml(rsr, tmp_path):
    path = tmp_path / "inventory" / "group_vars" / "all" / "platform_services.yml"
    path.parent.mkdir(parents=True)
    path.write_text("[: not valid yaml")
    assert rsr.load_service_registry_roles(tmp_path) == {}


def test_candidate_role_paths_uses_registry_roles_when_present(rsr, tmp_path):
    """When the registry declares explicit roles, they are picked up
    even when the heuristic naming convention misses."""
    _write_registry(tmp_path, {"oddly_named": ["alpha_kit", "beta_kit"]})
    (tmp_path / "roles" / "alpha_kit").mkdir(parents=True)
    (tmp_path / "roles" / "beta_kit").mkdir(parents=True)
    out = rsr.candidate_role_paths("oddly_named", tmp_path)
    assert "roles/alpha_kit" in out
    assert "roles/beta_kit" in out


def test_candidate_role_paths_registry_then_heuristic_no_dupes(rsr, tmp_path):
    """Registry entry pointing at one role + heuristic finding another
    must yield the union, not duplicates."""
    _write_registry(tmp_path, {"alpha": ["alpha_kit"]})
    (tmp_path / "roles" / "alpha_kit").mkdir(parents=True)
    (tmp_path / "roles" / "alpha_runtime").mkdir(parents=True)  # heuristic
    out = rsr.candidate_role_paths("alpha", tmp_path)
    assert "roles/alpha_kit" in out
    assert "roles/alpha_runtime" in out
    # No duplicates.
    assert len(out) == len(set(out))


def test_candidate_role_paths_registry_role_in_collection_mirror(rsr, tmp_path):
    """Registry roles also probe the collections mirror."""
    _write_registry(tmp_path, {"alpha": ["alpha_kit"]})
    mirror = tmp_path / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "alpha_kit"
    mirror.mkdir(parents=True)
    out = rsr.candidate_role_paths("alpha", tmp_path)
    assert any("collections/ansible_collections" in p for p in out)


def test_classify_uses_registry_to_unblock_unknowns(rsr, tmp_path, monkeypatch):
    """A service that the heuristic alone can't find a role for, but
    that the registry maps to a real role, should classify as
    safe_to_refresh / needs_review (not unknown)."""
    _write_registry(tmp_path, {"oddly_named": ["alpha_kit"]})
    (tmp_path / "roles" / "alpha_kit").mkdir(parents=True)
    monkeypatch.setattr(rsr, "changed_since", lambda paths, *, since, repo_root: [])
    receipts = {"oddly_named": "2026-01-01-x"}
    today = dt.date(2026, 4, 28)
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=tmp_path)
    assert c.summary()["safe_to_refresh"] == 1
    assert c.summary()["unknown"] == 0


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def _setup_repo(tmp_path: Path, services: list[str]) -> Path:
    """Create role directories for each service. Returns repo_root."""
    for svc in services:
        (tmp_path / "roles" / f"{svc}_runtime").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_classify_ignores_fresh_receipts(rsr, tmp_path):
    """Receipts within the freshness window are not surfaced — only
    stale ones are classified into safe/needs/unknown."""
    repo_root = _setup_repo(tmp_path, ["fresh_svc"])
    receipts = {"fresh_svc": "2026-04-25-x"}
    today = dt.date(2026, 4, 28)  # 3 days old, default window 30
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=repo_root)
    assert c.summary()["total"] == 0


def test_classify_unknown_when_no_role_dir(rsr, tmp_path):
    """A stale receipt for a service whose role isn't on disk gets
    classified as unknown — we can't run a no-op converge for a role
    we don't have."""
    receipts = {"ghost_service": "2026-01-01-x"}
    today = dt.date(2026, 4, 28)
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=tmp_path)
    assert c.summary()["unknown"] == 1
    assert c.unknown[0].service == "ghost_service"


def test_classify_unknown_when_slug_unparseable(rsr, tmp_path):
    receipts = {"x": "no-date-here"}
    today = dt.date(2026, 4, 28)
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=tmp_path)
    assert c.unknown[0].service == "x"
    assert "missing YYYY-MM-DD" in c.unknown[0].reason


def test_classify_safe_when_no_changes_since(rsr, tmp_path, monkeypatch):
    """Stale receipt + role exists + no changes since receipt date → safe."""
    repo_root = _setup_repo(tmp_path, ["alpha"])
    monkeypatch.setattr(rsr, "changed_since", lambda paths, *, since, repo_root: [])
    receipts = {"alpha": "2026-01-01-x"}
    today = dt.date(2026, 4, 28)
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=repo_root)
    assert c.summary()["safe_to_refresh"] == 1
    assert c.safe_to_refresh[0].service == "alpha"
    assert c.safe_to_refresh[0].age_days == (today - dt.date(2026, 1, 1)).days


def test_classify_needs_review_when_changes_since(rsr, tmp_path, monkeypatch):
    """Stale receipt + role exists + changes since receipt date → needs_review."""
    repo_root = _setup_repo(tmp_path, ["beta"])
    monkeypatch.setattr(
        rsr,
        "changed_since",
        lambda paths, *, since, repo_root: ["roles/beta_runtime/tasks/main.yml"],
    )
    receipts = {"beta": "2026-01-01-x"}
    today = dt.date(2026, 4, 28)
    c = rsr.classify(receipts, today=today, max_age_days=30, repo_root=repo_root)
    assert c.summary()["needs_review"] == 1
    assert c.needs_review[0].service == "beta"
    assert "roles/beta_runtime/tasks/main.yml" in c.needs_review[0].changed_paths


def test_classify_handles_mixed_inputs(rsr, tmp_path, monkeypatch):
    repo_root = _setup_repo(tmp_path, ["alpha", "beta"])

    def fake_changed(paths, *, since, repo_root):
        if any("beta" in p for p in paths):
            return ["roles/beta_runtime/x.yml"]
        return []

    monkeypatch.setattr(rsr, "changed_since", fake_changed)
    receipts = {
        "alpha": "2026-01-01-x",  # stale, no change → safe
        "beta": "2026-01-01-x",  # stale, change → needs_review
        "gamma": "2026-01-01-x",  # stale, no role → unknown
        "fresh": "2026-04-25-x",  # fresh → ignored
        "weird": "no-date",  # unparseable → unknown
    }
    c = rsr.classify(receipts, today=dt.date(2026, 4, 28), max_age_days=30, repo_root=repo_root)
    s = c.summary()
    assert s["safe_to_refresh"] == 1
    assert s["needs_review"] == 1
    assert s["unknown"] == 2  # gamma + weird; fresh is silently ignored


# ---------------------------------------------------------------------------
# refresh_receipt_slug
# ---------------------------------------------------------------------------


def test_refresh_receipt_slug_replaces_date_prefix(rsr):
    new = rsr.refresh_receipt_slug("2026-01-01-foo-bar", dt.date(2026, 4, 28))
    assert new == "2026-04-28-foo-bar"


def test_refresh_receipt_slug_leaves_unparseable_alone(rsr):
    assert rsr.refresh_receipt_slug("no-date-here", dt.date(2026, 4, 28)) == "no-date-here"


# ---------------------------------------------------------------------------
# apply_safe_refresh
# ---------------------------------------------------------------------------


def test_apply_safe_refresh_updates_only_safe_set(rsr, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(
        yaml.safe_dump(
            {
                "live_apply_evidence": {
                    "receipt_dir": "receipts/live-applies",
                    "latest_receipts": {
                        "alpha": "2026-01-01-old-stable",
                        "beta": "2026-01-01-old-changed",
                    },
                }
            }
        )
    )
    classification = rsr.Classification(
        safe_to_refresh=[
            rsr.SafeEntry(
                service="alpha",
                slug="2026-01-01-old-stable",
                receipt_date="2026-01-01",
                age_days=117,
            )
        ],
        needs_review=[
            rsr.NeedsReviewEntry(
                service="beta",
                slug="2026-01-01-old-changed",
                receipt_date="2026-01-01",
                age_days=117,
                changed_paths=["roles/beta_runtime/x.yml"],
            )
        ],
    )
    count = rsr.apply_safe_refresh(
        classification,
        today=dt.date(2026, 4, 28),
        stack_yaml_path=stack,
    )
    assert count == 1
    loaded = yaml.safe_load(stack.read_text())
    receipts = loaded["live_apply_evidence"]["latest_receipts"]
    assert receipts["alpha"] == "2026-04-28-old-stable"  # refreshed
    assert receipts["beta"] == "2026-01-01-old-changed"  # left alone


def test_apply_safe_refresh_zero_when_safe_set_empty(rsr, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": {}}}))
    c = rsr.Classification()
    assert rsr.apply_safe_refresh(c, today=dt.date(2026, 4, 28), stack_yaml_path=stack) == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_json_emits_summary(rsr, tmp_path, capsys):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": {}}}))
    rc = rsr.main(["--stack-yaml", str(stack), "--root", str(tmp_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["total"] == 0


def test_cli_apply_refuses_dirty_tree(rsr, tmp_path, monkeypatch, capsys):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": {}}}))
    monkeypatch.setattr(rsr, "working_tree_clean", lambda repo_root: False)
    rc = rsr.main(["--apply", "--stack-yaml", str(stack), "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "dirty" in err.lower()


def test_cli_negative_max_age_days_returns_two(rsr, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": {}}}))
    rc = rsr.main(["--stack-yaml", str(stack), "--max-age-days", "-1"])
    assert rc == 2
