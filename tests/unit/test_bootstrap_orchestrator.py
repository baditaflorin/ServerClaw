"""Unit tests for scripts/bootstrap_orchestrator.py — ADR 0483.

Tests the pure helpers only (no subprocess invocations, no make calls).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from bootstrap_orchestrator import (
    BootstrapReceipt,
    ConditionResult,
    StepResult,
    build_template_ctx,
    evaluate_condition,
    expand_templates,
    format_status,
    load_last_failure_receipt,
    orchestrate,
    select_steps,
    step_status,
)


# ---------------------------------------------------------------------------
# select_steps
# ---------------------------------------------------------------------------


SAMPLE_STEPS = [
    {"id": "0-derive", "make_target": "derive-deployment-files"},
    {"id": "1-probe-capacity", "make_target": "probe-capacity"},
    {"id": "2-resolve-topology", "make_target": "resolve-topology"},
    {"id": "3-init-remote", "make_target": "init-remote"},
]


class TestSelectSteps:
    def test_no_resume_returns_all(self):
        assert select_steps(SAMPLE_STEPS) == SAMPLE_STEPS

    def test_resume_from_first_step_returns_all(self):
        result = select_steps(SAMPLE_STEPS, resume_from="0-derive")
        assert len(result) == 4

    def test_resume_from_middle_skips_earlier(self):
        result = select_steps(SAMPLE_STEPS, resume_from="2-resolve-topology")
        assert len(result) == 2
        assert result[0]["id"] == "2-resolve-topology"

    def test_resume_from_last_returns_one(self):
        result = select_steps(SAMPLE_STEPS, resume_from="3-init-remote")
        assert len(result) == 1
        assert result[0]["id"] == "3-init-remote"

    def test_resume_from_unknown_raises(self):
        with pytest.raises(ValueError, match="not found"):
            select_steps(SAMPLE_STEPS, resume_from="99-nonexistent")

    def test_empty_steps_no_resume(self):
        assert select_steps([]) == []


# ---------------------------------------------------------------------------
# build_template_ctx
# ---------------------------------------------------------------------------


class TestBuildTemplateCtx:
    def test_apex(self):
        ctx = build_template_ctx({"platform_domain": "example.org"})
        assert ctx["apex"] == "example.org"
        assert ctx["apex_slug"] == "0fork"

    def test_empty_identity(self):
        ctx = build_template_ctx({})
        assert ctx["apex"] == ""
        assert ctx["apex_slug"] == ""

    def test_multi_label_domain(self):
        ctx = build_template_ctx({"platform_domain": "lv3.example.com"})
        assert ctx["apex_slug"] == "lv3"


# ---------------------------------------------------------------------------
# expand_templates
# ---------------------------------------------------------------------------


class TestExpandTemplates:
    def test_replaces_slug(self):
        ctx = {"slug": "0fork", "apex": "example.org"}
        assert expand_templates(ctx, "{slug}/manifest.yml") == "0fork/manifest.yml"

    def test_replaces_in_list(self):
        ctx = {"slug": "0fork"}
        result = expand_templates(ctx, ["{slug}.yml", "other"])
        assert result == ["0fork.yml", "other"]

    def test_replaces_in_dict(self):
        ctx = {"apex": "example.org"}
        result = expand_templates(ctx, {"path": ".local/{apex}/x"})
        assert result["path"] == ".local/example.org/x"

    def test_leaves_unknown_placeholder(self):
        ctx = {}
        assert expand_templates(ctx, "{unknown}") == "{unknown}"

    def test_non_string_passthrough(self):
        ctx = {"slug": "x"}
        assert expand_templates(ctx, 42) == 42
        assert expand_templates(ctx, True) is True


# ---------------------------------------------------------------------------
# evaluate_condition — file type
# ---------------------------------------------------------------------------


class TestEvaluateConditionFile:
    def test_existing_file_expect_exists_true(self, tmp_path):
        f = tmp_path / "test.yml"
        f.write_text("a: 1")
        cond = {"id": "test.file", "type": "file", "path": "test.yml", "expect_exists": True}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is True

    def test_missing_file_expect_exists_true(self, tmp_path):
        cond = {"id": "test.file", "type": "file", "path": "missing.yml", "expect_exists": True}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False

    def test_missing_file_expect_exists_false(self, tmp_path):
        cond = {"id": "test.file", "type": "file", "path": "missing.yml", "expect_exists": False}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is True

    def test_existing_file_expect_exists_false(self, tmp_path):
        f = tmp_path / "test.yml"
        f.write_text("x: 1")
        cond = {"id": "test.file", "type": "file", "path": "test.yml", "expect_exists": False}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False

    def test_default_expect_exists_is_true(self, tmp_path):
        f = tmp_path / "x.yml"
        f.write_text("a: 1")
        cond = {"id": "c", "type": "file", "path": "x.yml"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is True


# ---------------------------------------------------------------------------
# evaluate_condition — schema type
# ---------------------------------------------------------------------------


class TestEvaluateConditionSchema:
    def test_valid_yaml_passes(self, tmp_path):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        (tmp_path / "schema.json").write_text(json.dumps(schema))
        (tmp_path / "target.yml").write_text("name: hello")
        cond = {"id": "c", "type": "schema", "target": "target.yml", "schema": "schema.json"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is True

    def test_invalid_yaml_fails(self, tmp_path):
        schema = {"type": "object", "required": ["name"]}
        (tmp_path / "schema.json").write_text(json.dumps(schema))
        (tmp_path / "target.yml").write_text("other: hello")
        cond = {"id": "c", "type": "schema", "target": "target.yml", "schema": "schema.json"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False

    def test_missing_target_fails(self, tmp_path):
        schema = {"type": "object"}
        (tmp_path / "schema.json").write_text(json.dumps(schema))
        cond = {"id": "c", "type": "schema", "target": "missing.yml", "schema": "schema.json"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False

    def test_missing_schema_fails(self, tmp_path):
        (tmp_path / "target.yml").write_text("name: hello")
        cond = {"id": "c", "type": "schema", "target": "target.yml", "schema": "missing.json"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False


# ---------------------------------------------------------------------------
# evaluate_condition — unknown type
# ---------------------------------------------------------------------------


class TestEvaluateConditionUnknown:
    def test_unknown_type_fails(self, tmp_path):
        cond = {"id": "c", "type": "telekinesis"}
        result = evaluate_condition(cond, repo_root=tmp_path)
        assert result.ok is False
        assert "unknown" in result.observed


# ---------------------------------------------------------------------------
# step_status
# ---------------------------------------------------------------------------


class TestStepStatus:
    def test_skipped(self):
        r = StepResult(step_id="1-probe", make_target="probe", status="skipped")
        assert "SKIP" in step_status(r)
        assert "1-probe" in step_status(r)

    def test_passed(self):
        r = StepResult(step_id="1-probe", make_target="probe", status="passed", duration_s=3.5)
        line = step_status(r)
        assert "PASS" in line
        assert "3.5s" in line

    def test_failed_postcondition(self):
        r = StepResult(step_id="1-probe", make_target="probe", status="failed")
        r.postcondition_results.append(ConditionResult("cap.exists", False, "missing: /tmp/cap.yml"))
        line = step_status(r)
        assert "FAIL" in line
        assert "cap.exists" in line

    def test_failed_precondition(self):
        r = StepResult(step_id="1-probe", make_target="probe", status="failed")
        r.precondition_results.append(ConditionResult("conn.exists", False, "missing"))
        line = step_status(r)
        assert "FAIL" in line
        assert "conn.exists" in line

    def test_error(self):
        r = StepResult(step_id="1-probe", make_target="probe", status="error", error="make timed out")
        line = step_status(r)
        assert "ERR" in line
        assert "timed out" in line


# ---------------------------------------------------------------------------
# format_status
# ---------------------------------------------------------------------------


class TestFormatStatus:
    def test_success_receipt(self):
        receipt = {
            "deployment": "example.org",
            "outcome": "success",
            "ran_at": "2026-05-13T00:00:00Z",
            "steps_passed": 14,
            "steps_failed": 0,
            "steps_skipped": 0,
            "step_results": [{"step_id": "0-derive", "status": "passed"}],
        }
        out = format_status(receipt)
        assert "0fork" in out
        assert "success" in out
        assert "14" in out
        assert "✓" in out

    def test_failure_receipt(self):
        receipt = {
            "deployment": "example.org",
            "outcome": "failure",
            "ran_at": "2026-05-13T00:00:00Z",
            "steps_passed": 3,
            "steps_failed": 1,
            "steps_skipped": 10,
            "failed_step_id": "3-init-remote",
            "step_results": [
                {"step_id": "0-derive", "status": "passed"},
                {"step_id": "3-init-remote", "status": "failed"},
            ],
        }
        out = format_status(receipt)
        assert "failure" in out
        assert "3-init-remote" in out
        assert "✗" in out


# ---------------------------------------------------------------------------
# load_last_failure_receipt
# ---------------------------------------------------------------------------


class TestLoadLastFailureReceipt:
    def test_no_dir_returns_none(self, tmp_path):
        result = load_last_failure_receipt(receipts_dir=tmp_path / "nonexistent")
        assert result is None

    def test_empty_dir_returns_none(self, tmp_path):
        result = load_last_failure_receipt(receipts_dir=tmp_path)
        assert result is None

    def test_returns_most_recent(self, tmp_path):
        r1 = {"deployment": "example.com", "outcome": "failure", "failed_step_id": "1-probe"}
        r2 = {"deployment": "example.com", "outcome": "failure", "failed_step_id": "3-init"}
        (tmp_path / "2026-05-10T00-00-00Z-bootstrap-1-probe-failure.json").write_text(json.dumps(r1))
        (tmp_path / "2026-05-13T00-00-00Z-bootstrap-3-init-failure.json").write_text(json.dumps(r2))
        result = load_last_failure_receipt(receipts_dir=tmp_path)
        assert result is not None
        assert result["failed_step_id"] == "3-init"


# ---------------------------------------------------------------------------
# orchestrate — integration (no make calls via dry_run=True)
# ---------------------------------------------------------------------------


class TestOrchestrate:
    def _make_steps(self, n: int = 3) -> list[dict]:
        return [
            {
                "id": f"{i}-step",
                "make_target": f"target-{i}",
                "preconditions": [],
                "postconditions": [],
            }
            for i in range(n)
        ]

    def test_dry_run_all_pass(self, tmp_path):
        steps = self._make_steps(3)
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": True, "max_retries_per_step": 0},
            dry_run=True,
            write_receipt=False,
        )
        assert receipt.outcome == "success"
        assert receipt.steps_passed == 3
        assert receipt.steps_failed == 0

    def test_resume_from_skips_earlier(self, tmp_path):
        steps = self._make_steps(4)
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": True},
            resume_from="2-step",
            dry_run=True,
            write_receipt=False,
        )
        assert receipt.steps_skipped == 2
        assert receipt.steps_passed == 2

    def test_precondition_failure_stops_step(self, tmp_path):
        steps = [
            {
                "id": "0-step",
                "make_target": "t",
                "preconditions": [{"id": "pre.file", "type": "file", "path": "missing.yml", "expect_exists": True}],
                "postconditions": [],
            }
        ]
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": True},
            dry_run=False,
            write_receipt=False,
            repo_root=tmp_path,
        )
        assert receipt.outcome == "failure"
        assert receipt.step_results[0].status == "failed"
        assert receipt.step_results[0].make_exit_code is None

    def test_fail_fast_skips_remaining(self, tmp_path):
        steps = [
            {
                "id": "0-fail",
                "make_target": "t",
                "preconditions": [{"id": "pre.miss", "type": "file", "path": "no.yml"}],
                "postconditions": [],
            },
            {"id": "1-after", "make_target": "t2", "preconditions": [], "postconditions": []},
            {"id": "2-after", "make_target": "t3", "preconditions": [], "postconditions": []},
        ]
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": True},
            dry_run=False,
            write_receipt=False,
            repo_root=tmp_path,
        )
        assert receipt.steps_failed == 1
        assert receipt.steps_skipped == 2
        assert receipt.outcome == "failure"

    def test_no_fail_fast_continues(self, tmp_path):
        steps = [
            {
                "id": "0-fail",
                "make_target": "t",
                "preconditions": [{"id": "pre.miss", "type": "file", "path": "no.yml"}],
                "postconditions": [],
            },
            {"id": "1-ok", "make_target": "t2", "preconditions": [], "postconditions": []},
        ]
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": False},
            dry_run=True,
            write_receipt=False,
            repo_root=tmp_path,
        )
        # step 0 fails on precondition (no dry_run bypass for preconditions)
        # step 1 runs because fail_fast=False
        assert receipt.steps_failed == 1
        assert receipt.steps_passed >= 1

    def test_receipt_written_on_success(self, tmp_path):
        steps = self._make_steps(1)
        receipts_dir = tmp_path / "receipts"
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={},
            dry_run=True,
            write_receipt=True,
            receipts_dir=receipts_dir,
        )
        assert receipt.outcome == "success"
        written = list(receipts_dir.glob("*-bootstrap-receipt.json"))
        assert len(written) == 1

    def test_receipt_written_on_failure(self, tmp_path):
        steps = [
            {
                "id": "0-fail",
                "make_target": "t",
                "preconditions": [{"id": "pre", "type": "file", "path": "no.yml"}],
                "postconditions": [],
            }
        ]
        receipts_dir = tmp_path / "receipts"
        receipt = orchestrate(
            steps,
            "0fork",
            ctx={"apex": "example.org", "apex_slug": "0fork"},
            gates={"fail_fast": True},
            dry_run=False,
            write_receipt=True,
            receipts_dir=receipts_dir,
            repo_root=tmp_path,
        )
        assert receipt.outcome == "failure"
        written = list(receipts_dir.glob("*failure*.json"))
        assert len(written) == 1
