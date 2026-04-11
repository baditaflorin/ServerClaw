from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_TRIAGE_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "run-triage.py"
CALIBRATE_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "calibrate-triage-rules.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_run_triage_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("run_triage_windmill", RUN_TRIAGE_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_run_triage_imports_repo_script(tmp_path: Path) -> None:
    module = load_module("run_triage_windmill_import", RUN_TRIAGE_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "incident_triage.py").write_text(
        """
def build_report(payload, loki_query_url=None):
    return {"incident_id": "inc-1", "affected_service": payload["service_id"], "hypotheses": [], "signal_set": {}, "elapsed_ms": 1}

def emit_triage_report(report, emit_audit, mattermost_webhook_url):
    return {"report_path": "/tmp/report.json", "mattermost_posted": False}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = module.main(alert_payload={"service_id": "netbox"}, repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["emission"]["mattermost_posted"] is False


def test_calibration_wrapper_posts_optional_summary(monkeypatch, tmp_path: Path) -> None:
    module = load_module("calibrate_triage_windmill", CALIBRATE_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "triage_calibration.py").write_text(
        """
from pathlib import Path

def calibrate(cases_path=None):
    return {"status": "ok", "summary": {"reports_reviewed": 2, "cases_reviewed": 1, "rules_with_data": 1}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(
        module, "post_json_webhook", lambda url, payload: captured.update({"url": url, "payload": payload})
    )

    payload = module.main(repo_path=str(repo_root), mattermost_webhook_url="https://example.invalid/webhook")

    assert payload["status"] == "ok"
    assert payload["mattermost_posted"] is True
    assert captured["url"] == "https://example.invalid/webhook"
