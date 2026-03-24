from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "platform-observation-loop.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("platform_observation_loop_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_wrapper_processes_actionable_findings(tmp_path: Path) -> None:
    module = load_module("platform_observation_loop_ok", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config" / "service-capability-catalog.json").write_text(
        json.dumps({"services": [{"id": "netbox", "name": "NetBox", "lifecycle_status": "active"}]}) + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-catalog.json").write_text(
        json.dumps({"workflows": {"converge-netbox": {"description": "Converge", "live_impact": "guest_live"}}}) + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "controller-local-secrets.json").write_text(json.dumps({"secrets": {}}) + "\n", encoding="utf-8")
    (repo_root / "scripts" / "incident_triage.py").write_text(
        """
def build_report(payload):
    return {
        "affected_service": payload["service_id"],
        "hypotheses": [{"rank": 1, "id": "tls-cert-expiry", "auto_check": True, "cheapest_first_action": "check cert"}],
        "auto_check_result": {"status": "executed", "type": "cert_check"},
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = module.main(
        findings=[{"severity": "critical", "check": "check-service-health", "service_id": "netbox"}],
        repo_path=str(repo_root),
    )

    assert payload["status"] == "ok"
    assert payload["processed_count"] == 1
    assert payload["processed_runs"][0]["service_id"] == "netbox"
