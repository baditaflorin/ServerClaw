"""Unit tests for scripts/apply_promotion.py — ADR 0465 phase 9.2.

Exercises plan synthesis (parsing validate_repo.sh, matching gates
against ALLOWED_GATES, computing the line edit) and the apply path
(rewriting the file + seeding ledger entries) against synthetic
fixtures. The live tracker integration is bypassed via --gates.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "apply_promotion.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("apply_promotion", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["apply_promotion"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ap():
    return _load_module()


_SYNTHETIC_SH = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    validate_no_hardcoded_topology() {
      echo "Topology hardcode validation (ADR 0443 — advisory)"
      run scripts/validate_no_hardcoded_topology.py
    }

    validate_catalogue_freshness() {
      echo "Validator catalogue freshness (ADR 0449 — advisory)"
      scripts/generate_validator_catalogue.py --check
    }

    validate_traceability() {
      echo "Workstream traceability (ADR 0447 — advisory)"
      scripts/generate_traceability.py --validate
    }

    validate_random_thing() {
      echo "Random thing (ADR 0099 — advisory)"
      true
    }
    """
)


def _setup_repo(tmp_path: Path, sh_text: str = _SYNTHETIC_SH) -> Path:
    """Lay out tmp_path as a faux repo root with scripts/validate_repo.sh."""
    sh = tmp_path / "scripts" / "validate_repo.sh"
    sh.parent.mkdir(parents=True)
    sh.write_text(sh_text)
    return tmp_path


# ---------------------------------------------------------------------------
# find_advisory_line
# ---------------------------------------------------------------------------


def test_find_advisory_line_picks_up_inside_function(ap):
    """The advisory annotation inside the gate's bash function is
    located by line number + verbatim line text."""
    out = ap.find_advisory_line(_SYNTHETIC_SH, "validate_no_hardcoded_topology")
    assert out is not None
    line_number, line = out
    assert "ADR 0443" in line
    assert "advisory" in line


def test_find_advisory_line_handles_em_dash(ap):
    """The annotation uses an em-dash; the regex tolerates both
    em-dash and hyphen."""
    sh = 'validate_x() {\n  echo "Foo (ADR 0001 - advisory)"\n}\n'
    assert ap.find_advisory_line(sh, "validate_x") is not None


def test_find_advisory_line_returns_none_for_unknown_function(ap):
    assert ap.find_advisory_line(_SYNTHETIC_SH, "ghost_gate") is None


def test_find_advisory_line_only_inside_function_block(ap):
    """A line outside the gate's function block is not flagged.
    Otherwise a comment in another function could trick the rewriter."""
    sh = dedent(
        """\
        validate_alpha() {
          echo "alpha"
        }

        # (ADR 0123 — advisory) — this is a comment, not inside any gate function.
        validate_beta() {
          echo "beta no annotation"
        }
        """
    )
    # Neither function should match — alpha has no annotation; beta
    # doesn't either; the rogue comment is between them.
    assert ap.find_advisory_line(sh, "validate_alpha") is None
    assert ap.find_advisory_line(sh, "validate_beta") is None


# ---------------------------------------------------------------------------
# synthesise_plan
# ---------------------------------------------------------------------------


def test_synthesise_plan_picks_only_allowed_gates(ap, tmp_path):
    eligible = [
        {"gate": "validate_no_hardcoded_topology", "rule": None, "status": "eligible"},
        {"gate": "validate_random_thing", "rule": None, "status": "eligible"},
    ]
    plan, skipped = ap.synthesise_plan(eligible, _SYNTHETIC_SH, repo_root=tmp_path)
    assert len(plan) == 1
    assert plan[0].gate == "validate_no_hardcoded_topology"
    assert any("validate_random_thing" in s for s in skipped)
    assert "ALLOWED_GATES" in skipped[0]


def test_synthesise_plan_rewrites_advisory_to_required(ap, tmp_path):
    eligible = [{"gate": "validate_no_hardcoded_topology", "rule": None, "status": "eligible"}]
    plan, skipped = ap.synthesise_plan(eligible, _SYNTHETIC_SH, repo_root=tmp_path)
    step = plan[0]
    assert "advisory" in step.line_before
    assert "required" in step.line_after
    assert "advisory" not in step.line_after


def test_synthesise_plan_skips_when_no_advisory_annotation(ap, tmp_path):
    """A gate that's eligible but doesn't carry the `(ADR NNNN —
    advisory)` annotation is skipped — the rewriter has nothing to
    edit."""
    sh = 'validate_catalogue_freshness() {\n  echo "no annotation here"\n}\n'
    eligible = [{"gate": "validate_catalogue_freshness", "rule": None, "status": "eligible"}]
    plan, skipped = ap.synthesise_plan(eligible, sh, repo_root=tmp_path)
    assert plan == []
    assert any("no `(ADR NNNN — advisory)`" in s for s in skipped)


def test_synthesise_plan_handles_unnamed_gate(ap, tmp_path):
    eligible = [{"rule": None, "status": "eligible"}]  # no `gate` field
    plan, skipped = ap.synthesise_plan(eligible, _SYNTHETIC_SH, repo_root=tmp_path)
    assert plan == []
    assert any("missing 'gate'" in s for s in skipped)


# ---------------------------------------------------------------------------
# apply_plan
# ---------------------------------------------------------------------------


def test_apply_plan_rewrites_file_and_seeds_ledger(ap, tmp_path):
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    eligible = [{"gate": "validate_no_hardcoded_topology", "rule": None, "status": "eligible"}]
    plan, _ = ap.synthesise_plan(eligible, sh_path.read_text(), repo_root=repo_root)
    applied = ap.apply_plan(plan, sh_path=sh_path, repo_root=repo_root, today=dt.date(2026, 4, 29))
    assert applied == 1
    text = sh_path.read_text()
    assert "ADR 0443 — required" in text or "ADR 0443 - required" in text
    assert "ADR 0443 — advisory" not in text
    # Ledger entry created.
    seed = repo_root / "receipts" / "gate-runs" / "validate_no_hardcoded_topology"
    assert seed.is_dir()
    seed_files = list(seed.glob("*.yaml"))
    assert len(seed_files) == 1
    payload = yaml.safe_load(seed_files[0].read_text())
    assert payload["mode"] == "required"
    assert payload["result"] == "clean"


def test_apply_plan_idempotent_after_rewrite(ap, tmp_path):
    """Applying the same plan twice rewrites only once — the second
    pass sees the updated line and skips."""
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    eligible = [{"gate": "validate_no_hardcoded_topology", "rule": None, "status": "eligible"}]
    plan, _ = ap.synthesise_plan(eligible, sh_path.read_text(), repo_root=repo_root)
    ap.apply_plan(plan, sh_path=sh_path, repo_root=repo_root, today=dt.date(2026, 4, 29))
    # Re-synthesise plan — there should be no advisory line anymore.
    plan2, _ = ap.synthesise_plan(eligible, sh_path.read_text(), repo_root=repo_root)
    assert plan2 == []  # nothing to rewrite


def test_apply_plan_handles_empty(ap, tmp_path):
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    assert ap.apply_plan([], sh_path=sh_path, repo_root=repo_root) == 0


def test_apply_plan_skips_step_when_line_drifted(ap, tmp_path):
    """If the file changed since the plan was synthesised (concurrent
    edit), the step is skipped — the line_before snapshot doesn't
    match disk anymore."""
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    eligible = [{"gate": "validate_no_hardcoded_topology", "rule": None, "status": "eligible"}]
    plan, _ = ap.synthesise_plan(eligible, sh_path.read_text(), repo_root=repo_root)
    # Mutate the file out from under the plan.
    sh_path.write_text(sh_path.read_text().replace("advisory", "advisory  # some operator note"))
    applied = ap.apply_plan(plan, sh_path=sh_path, repo_root=repo_root)
    assert applied == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_does_not_mutate(ap, tmp_path, capsys):
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    original = sh_path.read_text()
    rc = ap.main(
        [
            "--root",
            str(repo_root),
            "--gates",
            "validate_no_hardcoded_topology",
        ]
    )
    assert rc == 0
    assert sh_path.read_text() == original  # no mutation
    out = capsys.readouterr().out
    assert "ready to promote" in out
    assert "Pass --apply" in out


def test_cli_apply_mutates_when_clean(ap, tmp_path, capsys, monkeypatch):
    """`--apply` writes when the working tree is clean (mocked)."""
    repo_root = _setup_repo(tmp_path)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    monkeypatch.setattr(ap, "working_tree_clean", lambda path, repo_root: True)
    rc = ap.main(
        [
            "--root",
            str(repo_root),
            "--gates",
            "validate_no_hardcoded_topology",
            "--apply",
        ]
    )
    assert rc == 0
    assert "advisory" not in sh_path.read_text() or "ADR 0443 — required" in sh_path.read_text()


def test_cli_apply_refuses_dirty_tree(ap, tmp_path, capsys, monkeypatch):
    repo_root = _setup_repo(tmp_path)
    monkeypatch.setattr(ap, "working_tree_clean", lambda path, repo_root: False)
    rc = ap.main(
        [
            "--root",
            str(repo_root),
            "--gates",
            "validate_no_hardcoded_topology",
            "--apply",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "uncommitted" in err or "refused" in err


def test_cli_no_eligible_gates_emits_clean_message(ap, tmp_path, capsys):
    repo_root = _setup_repo(tmp_path)
    rc = ap.main(["--root", str(repo_root)])  # no --gates, tracker returns []
    assert rc == 0
    out = capsys.readouterr().out
    assert "no eligible gates" in out


def test_cli_json_output(ap, tmp_path, capsys):
    repo_root = _setup_repo(tmp_path)
    rc = ap.main(
        [
            "--root",
            str(repo_root),
            "--gates",
            "validate_no_hardcoded_topology,validate_random_thing",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["would_apply_count"] == 1
    assert len(payload["skipped"]) == 1


def test_cli_missing_validate_repo_sh_returns_two(ap, tmp_path, capsys):
    rc = ap.main(["--root", str(tmp_path)])  # no scripts/ at all
    assert rc == 2
    err = capsys.readouterr().err
    assert "validate_repo.sh" in err
