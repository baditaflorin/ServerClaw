from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "nightly-integration-tests.py"
SPEC = importlib.util.spec_from_file_location("nightly_integration_tests", SCRIPT_PATH)
nightly_integration_tests = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(nightly_integration_tests)


def test_workflow_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = nightly_integration_tests.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_workflow_runs_suite_and_returns_payload(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / ".local" / "integration-tests").mkdir(parents=True)

    fake_module = type("FakeIntegrationSuite", (), {})()

    def fake_run_suite(**kwargs):
        assert kwargs["repo_root"] == tmp_path
        assert kwargs["mode"] == "nightly"
        return 0, {
            "status": "passed",
            "environment": "production",
            "mode": "nightly",
            "summary": {"passed": 4, "failed": 0, "skipped": 2},
            "tests": [],
            "duration_seconds": 1.23,
        }

    fake_module.run_suite = fake_run_suite
    monkeypatch.setattr(nightly_integration_tests, "publish_notifications", lambda repo_root, payload: None)
    monkeypatch.setitem(__import__("sys").modules, "integration_suite", fake_module)

    payload = nightly_integration_tests.main(repo_path=str(tmp_path))

    assert payload["status"] == "passed"


def test_workflow_loads_environment_catalog_from_repo_path(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / ".local" / "integration-tests").mkdir(parents=True)
    (tmp_path / "scripts" / "environment_catalog.py").write_text(
        "def environment_choices():\n"
        "    return ['production', 'staging']\n"
        "def primary_environment():\n"
        "    return 'staging'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(nightly_integration_tests, "publish_notifications", lambda repo_root, payload: None)
    monkeypatch.setattr(
        nightly_integration_tests,
        "execute_suite",
        lambda repo_root, environment, report_file: {"status": "passed", "environment": environment, "mode": "nightly", "summary": {"passed": 1, "failed": 0, "skipped": 0}, "tests": [], "duration_seconds": 0.1},
    )
    sys.modules.pop("environment_catalog", None)

    payload = nightly_integration_tests.main(repo_path=str(tmp_path))

    assert payload["environment"] == "staging"
