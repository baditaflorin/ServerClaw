"""Unit tests for scripts/self_check.py — ADR 0484.

Covers the pure helpers (no IO) and the retry loop with injected plugins:

  * build_template_context() composes correctly from identity.yml shape.
  * expand_templates() substitutes scalars / lists / dicts; leaves unknown
    placeholders untouched (so they're visible in failures rather than silent
    blanks).
  * select_checks() honours --step / --tag / --id and respects the default
    "skip bootstrap-only" rule.
  * run_check() with a fake plugin verifies:
      - happy path passes on first attempt
      - flaky check retries until success
      - permanent failure exhausts retries and reports `fail`
      - exception bubbles through as `error` with last_err captured
      - unknown plugin type → `error`, never crashes the runner
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("self_check", SCRIPTS_DIR / "self_check.py")
self_check = importlib.util.module_from_spec(spec)
sys.modules["self_check"] = self_check  # dataclass introspection needs this
assert spec.loader is not None
spec.loader.exec_module(self_check)


# --------------------------------------------------------------------------- #
# build_template_context
# --------------------------------------------------------------------------- #


def test_template_context_full_identity():
    ctx = self_check.build_template_context(
        {
            "platform_domain": "mycorp.com",
            "platform_operator_email": "ops@mycorp.com",
            "platform_operator_name": "Acme Corp Ops",
        }
    )
    assert ctx == {
        "apex": "mycorp.com",
        "apex_slug": "mycorp",
        "operator_email": "ops@mycorp.com",
        "operator_name": "Acme Corp Ops",
    }


def test_template_context_handles_missing_fields():
    ctx = self_check.build_template_context({})
    assert ctx == {"apex": "", "apex_slug": "", "operator_email": "", "operator_name": ""}


# --------------------------------------------------------------------------- #
# expand_templates
# --------------------------------------------------------------------------- #


def test_expand_string():
    ctx = {"apex": "example.org", "apex_slug": "0fork"}
    assert self_check.expand_templates(ctx, "https://registry.{apex}/v2/") == "https://registry.example.org/v2/"


def test_expand_nested_dict_and_list():
    ctx = {"apex": "example.org"}
    value = {
        "url": "https://{apex}/",
        "expect_san": ["{apex}", "wiki.{apex}"],
        "nested": {"x": "{apex}-x"},
        "unrelated_int": 200,
    }
    result = self_check.expand_templates(ctx, value)
    assert result["url"] == "https://example.org/"
    assert result["expect_san"] == ["example.org", "wiki.example.org"]
    assert result["nested"]["x"] == "example.org-x"
    assert result["unrelated_int"] == 200


def test_expand_leaves_unknown_placeholders_literal():
    """Unknown placeholders pass through unchanged — visible in failures."""
    ctx = {"apex": "example.org"}
    s = self_check.expand_templates(ctx, "https://{unknown}/{apex}")
    assert s == "https://{unknown}/example.org"


# --------------------------------------------------------------------------- #
# select_checks
# --------------------------------------------------------------------------- #


def _reg(*checks):
    return {"schema_version": 1, "post_conditions": list(checks)}


def test_select_by_step():
    r = _reg(
        {"id": "a", "type": "http", "after_step": "x"},
        {"id": "b", "type": "http", "after_step": "y"},
    )
    selected = self_check.select_checks(r, step="x")
    assert [c["id"] for c in selected] == ["a"]


def test_select_by_tag():
    r = _reg(
        {"id": "a", "type": "http", "after_step": "x", "tags": ["smoke"]},
        {"id": "b", "type": "http", "after_step": "y", "tags": ["bootstrap"]},
    )
    selected = self_check.select_checks(r, tag="smoke")
    assert [c["id"] for c in selected] == ["a"]


def test_select_by_id_ignores_other_filters():
    r = _reg(
        {"id": "a", "type": "http", "after_step": "x", "tags": ["smoke"]},
        {"id": "b", "type": "http", "after_step": "y", "tags": ["bootstrap-only"]},
    )
    # Even though 'b' is tagged bootstrap-only, --id b returns it.
    selected = self_check.select_checks(r, only_id="b")
    assert [c["id"] for c in selected] == ["b"]


def test_default_mode_skips_bootstrap_only_tag():
    r = _reg(
        {"id": "a", "type": "http", "after_step": "x", "tags": ["smoke"]},
        {"id": "b", "type": "http", "after_step": "y", "tags": ["bootstrap-only"]},
    )
    selected = self_check.select_checks(r)
    assert [c["id"] for c in selected] == ["a"]


# --------------------------------------------------------------------------- #
# run_check — retry loop with injected plugin
# --------------------------------------------------------------------------- #


class StubPlugin:
    """Plugin that yields a sequence of (observed, ok) results."""

    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = 0

    def run(self, check, ctx):
        self.calls += 1
        if not self.sequence:
            raise RuntimeError("plugin called more times than expected")
        item = self.sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ck(**overrides):
    base = {"id": "x", "type": "stub", "after_step": "step", "critical": True}
    base.update(overrides)
    return base


class _NoSleep:
    def __init__(self):
        self.calls = 0

    def __call__(self, _seconds):
        self.calls += 1


def test_run_check_passes_on_first_attempt():
    plugin = StubPlugin([("observed", True)])
    sleep = _NoSleep()
    result = self_check.run_check(_ck(retries=3), {"stub": plugin}, {}, sleep=sleep, clock=lambda: 0.0)
    assert result.result == "pass"
    assert result.attempt == 1
    assert plugin.calls == 1
    assert sleep.calls == 0


def test_run_check_retries_until_success():
    plugin = StubPlugin([("first", False), ("second", False), ("third", True)])
    sleep = _NoSleep()
    result = self_check.run_check(
        _ck(retries=3, retry_backoff_s=0.0), {"stub": plugin}, {}, sleep=sleep, clock=lambda: 0.0
    )
    assert result.result == "pass"
    assert result.attempt == 3
    # sleep is called between attempts (2 backoffs for 3 attempts).
    assert sleep.calls == 2


def test_run_check_exhausts_retries_and_reports_fail():
    plugin = StubPlugin([("nope", False)] * 4)
    sleep = _NoSleep()
    result = self_check.run_check(_ck(retries=3), {"stub": plugin}, {}, sleep=sleep, clock=lambda: 0.0)
    assert result.result == "fail"
    assert result.attempt == 4
    assert result.observed == "nope"


def test_run_check_exception_becomes_error():
    plugin = StubPlugin([RuntimeError("boom"), RuntimeError("boom2")])
    sleep = _NoSleep()
    result = self_check.run_check(_ck(retries=1), {"stub": plugin}, {}, sleep=sleep, clock=lambda: 0.0)
    assert result.result == "error"
    assert "boom2" in (result.error or "")


def test_run_check_unknown_plugin_type_is_error_not_crash():
    result = self_check.run_check(_ck(type="nonexistent-type"), {}, {})
    assert result.result == "error"
    assert "no plugin" in (result.error or "")


def test_run_check_template_expansion_applied_to_plugin_input():
    """Plugin receives the template-expanded check, not the raw one."""

    captured = {}

    class CapturingPlugin:
        def run(self, check, ctx):
            captured["url"] = check.get("url")
            return "ok", True

    self_check.run_check(
        _ck(type="cap", url="https://registry.{apex}/v2/"),
        {"cap": CapturingPlugin()},
        {"apex": "mycorp.com"},
    )
    assert captured["url"] == "https://registry.mycorp.com/v2/"


# --------------------------------------------------------------------------- #
# RunReport
# --------------------------------------------------------------------------- #


def test_run_report_categorizes_results():
    rep = self_check.RunReport(deployment="t", ran_at="2026-05-12T00:00:00Z")
    rep.add(self_check.CheckResult("a", "pass", True, "ok", 0.1))
    rep.add(self_check.CheckResult("b", "fail", True, "no", 0.1))  # critical fail
    rep.add(self_check.CheckResult("c", "fail", False, "no", 0.1))  # warning
    rep.add(self_check.CheckResult("d", "error", True, "boom", 0.1, error="x"))
    assert rep.passed == 1
    assert rep.failed_critical == 1
    assert rep.failed_warning == 1
    assert rep.errors == 1
    assert rep.total == 4
    out = rep.to_dict()
    assert out["summary"]["total"] == 4
    assert len(out["results"]) == 4
