"""Unit tests for scripts/lint_bootstrap_coverage.py — ADR 0484 §5."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from lint_bootstrap_coverage import lint_coverage, load_covered_steps, load_step_targets


def _write(tmp: Path, name: str, data: dict) -> Path:
    p = tmp / name
    p.write_text(yaml.dump(data, default_flow_style=False))
    return p


class TestLoadStepTargets:
    def test_extracts_make_targets(self, tmp_path):
        steps_file = _write(
            tmp_path,
            "steps.yml",
            {
                "schema_version": 1,
                "steps": [
                    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
                    {"id": "2-resolve-topology", "make_target": "resolve-topology"},
                ],
            },
        )
        targets = load_step_targets(steps_file)
        assert len(targets) == 2
        assert targets[0]["make_target"] == "probe-capacity"

    def test_omits_structural_steps(self, tmp_path):
        steps_file = _write(
            tmp_path,
            "steps.yml",
            {
                "schema_version": 1,
                "steps": [
                    {"id": "0-derive", "make_target": "derive-deployment-files"},
                    {"id": "12-final-smoke", "make_target": "self-check"},
                    {"id": "13-write-receipt", "make_target": "write-bootstrap-receipt"},
                    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
                ],
            },
        )
        targets = load_step_targets(steps_file)
        ids = [t["id"] for t in targets]
        assert "0-derive" not in ids
        assert "12-final-smoke" not in ids
        assert "13-write-receipt" not in ids
        assert "1-probe-capacity" in ids


class TestLoadCoveredSteps:
    def test_collects_after_step_values(self, tmp_path):
        cond_file = _write(
            tmp_path,
            "cond.yml",
            {
                "schema_version": 1,
                "post_conditions": [
                    {"id": "a.check", "after_step": "probe-capacity", "type": "file"},
                    {"id": "b.check", "after_step": "converge-harbor", "type": "http"},
                ],
            },
        )
        covered = load_covered_steps(cond_file)
        assert "probe-capacity" in covered
        assert "converge-harbor" in covered

    def test_skips_conditions_without_after_step(self, tmp_path):
        cond_file = _write(
            tmp_path,
            "cond.yml",
            {
                "schema_version": 1,
                "post_conditions": [
                    {"id": "a.check", "type": "file"},
                ],
            },
        )
        covered = load_covered_steps(cond_file)
        assert len(covered) == 0


class TestLintCoverage:
    def test_reports_missing_when_no_conditions(self, tmp_path):
        steps = _write(
            tmp_path,
            "steps.yml",
            {
                "schema_version": 1,
                "steps": [
                    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
                ],
            },
        )
        conds = _write(tmp_path, "cond.yml", {"schema_version": 1, "post_conditions": []})
        missing, present = lint_coverage(steps, conds)
        assert "1-probe-capacity" in missing
        assert "1-probe-capacity" not in present

    def test_reports_present_when_covered(self, tmp_path):
        steps = _write(
            tmp_path,
            "steps.yml",
            {
                "schema_version": 1,
                "steps": [
                    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
                ],
            },
        )
        conds = _write(
            tmp_path,
            "cond.yml",
            {
                "schema_version": 1,
                "post_conditions": [
                    {"id": "probe.file", "after_step": "probe-capacity", "type": "file"},
                ],
            },
        )
        missing, present = lint_coverage(steps, conds)
        assert "1-probe-capacity" not in missing
        assert "1-probe-capacity" in present

    def test_all_covered_returns_empty_missing(self, tmp_path):
        steps = _write(
            tmp_path,
            "steps.yml",
            {
                "schema_version": 1,
                "steps": [
                    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
                    {"id": "7-converge-edge", "make_target": "converge-edge-publication"},
                ],
            },
        )
        conds = _write(
            tmp_path,
            "cond.yml",
            {
                "schema_version": 1,
                "post_conditions": [
                    {"id": "a", "after_step": "probe-capacity", "type": "file"},
                    {"id": "b", "after_step": "converge-edge-publication", "type": "http"},
                ],
            },
        )
        missing, present = lint_coverage(steps, conds)
        assert missing == []
        assert len(present) == 2

    def test_real_files_are_fully_covered(self):
        """The actual config files should pass the lint."""
        from lint_bootstrap_coverage import CONDITIONS_PATH, STEPS_PATH

        missing, _ = lint_coverage(STEPS_PATH, CONDITIONS_PATH)
        assert missing == [], f"uncovered steps: {missing}"
