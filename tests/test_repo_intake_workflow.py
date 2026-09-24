from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_intake_make_target_has_a_governed_preflight_workflow() -> None:
    catalog = json.loads((REPO_ROOT / "config/workflow-catalog.json").read_text(encoding="utf-8"))
    workflow = catalog["workflows"]["converge-repo-intake"]

    assert workflow["preferred_entrypoint"]["target"] == "converge-repo-intake"
    assert workflow["preflight"]["required_secret_ids"] == [
        "bootstrap_ssh_private_key",
        "coolify_admin_auth",
    ]
    assert workflow["validation_targets"] == ["validate", "syntax-check-repo-intake"]
    assert workflow["live_impact"] == "guest_live"
    assert "docs/runbooks/repo-intake.md" == workflow["owner_runbook"]

    result = subprocess.run(
        [sys.executable, "scripts/preflight_controller_local.py", "--list"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "converge-repo-intake" in result.stdout


def test_repo_intake_command_requires_auth_boundary_and_live_apply_evidence() -> None:
    catalog = json.loads((REPO_ROOT / "config/command-catalog.json").read_text(encoding="utf-8"))
    command = catalog["commands"]["converge-repo-intake"]

    assert command["workflow_id"] == "converge-repo-intake"
    assert command["approval_policy"] == "sensitive_live_change"
    assert {item["name"] for item in command["inputs"]} == {
        "bootstrap_ssh_private_key",
        "coolify_admin_auth",
    }
    assert command["evidence"]["live_apply_receipt_required"] is True
    assert any("Authentik edge boundary" in item for item in command["failure_guidance"]["stop_conditions"])


def test_repo_intake_syntax_check_and_runbook_use_deployment_inventory() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "docs/runbooks/repo-intake.md").read_text(encoding="utf-8")

    assert "syntax-check-repo-intake:" in makefile
    assert "make preflight WORKFLOW=converge-repo-intake" in runbook
    assert "${PLATFORM_INVENTORY_OVERLAY:?select the deployment inventory}" in runbook
    assert "10.10.10." not in runbook
