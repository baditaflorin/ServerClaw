from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_service_catalog_marks_n8n_as_serverclaw_connector_fabric() -> None:
    catalog = load_json(REPO_ROOT / "config" / "service-capability-catalog.json")
    n8n = next(item for item in catalog["services"] if item["id"] == "n8n")

    assert "ServerClaw" in n8n["description"]
    assert "serverclaw" in n8n["tags"]
    assert "connector-fabric" in n8n["tags"]
    assert "ServerClaw connector calls" in n8n["environments"]["production"]["notes"]


def test_workflow_and_command_catalog_preserve_n8n_adapter_boundary() -> None:
    workflows = load_json(REPO_ROOT / "config" / "workflow-catalog.json")["workflows"]
    commands = load_json(REPO_ROOT / "config" / "command-catalog.json")["commands"]

    workflow = workflows["converge-n8n"]
    command = commands["converge-n8n"]

    assert "ServerClaw adapters" in workflow["description"]
    assert "thin ServerClaw adapters" in workflow["outputs"][0]
    assert any(
        "https://n8n.lv3.org/webhook-test/serverclaw-connector-smoke" in command_text
        for command_text in workflow["verification_commands"]
    )

    assert "ServerClaw connector fabric" in command["description"]
    assert any(
        "thin-adapter rule for ServerClaw" in precondition
        for precondition in command["expected_preconditions"]
    )
    assert "protected editor redirect" in command["evidence"]["notes"]


def test_runbook_documents_serverclaw_connector_boundary() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "configure-n8n.md").read_text(encoding="utf-8")

    assert "## ServerClaw Connector Boundary" in runbook
    assert "long-lived assistant state" in runbook
    assert "move that behavior back into the governed ServerClaw runtime boundary" in runbook
