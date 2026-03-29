from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_approval_routes_decision_through_policy_engine(monkeypatch) -> None:
    module = load_module("command_catalog_module", "scripts/command_catalog.py")
    captured: dict[str, Any] = {}

    def fake_policy(payload, *, repo_root=None, toolchain=None):  # type: ignore[no-untyped-def]
        captured["payload"] = payload
        return {
            "approved": True,
            "reasons": [],
            "workflow_id": "deploy-and-promote",
            "entrypoint": "make promote",
            "receipt_required": True,
        }

    monkeypatch.setattr(module, "evaluate_command_approval_policy", fake_policy)
    verdict = module.evaluate_approval(
        command_catalog={
            "approval_policies": {
                "operator_approved": {
                    "allowed_requester_classes": ["human_operator", "agent"],
                    "allowed_approver_classes": ["human_operator"],
                    "minimum_approvals": 1,
                    "require_preflight": True,
                    "require_validation": True,
                    "require_receipt_plan": True,
                    "allow_self_approval": False,
                    "allow_break_glass": False,
                }
            },
            "commands": {
                "promote-to-production": {
                    "workflow_id": "deploy-and-promote",
                    "approval_policy": "operator_approved",
                    "evidence": {"live_apply_receipt_required": True},
                }
            },
        },
        workflow_catalog={
            "workflows": {
                "deploy-and-promote": {
                    "lifecycle_status": "active",
                    "preferred_entrypoint": {"command": "make promote"},
                }
            }
        },
        command_id="promote-to-production",
        requester_class="human_operator",
        approver_classes=["human_operator"],
        preflight_passed=True,
        validation_passed=True,
        receipt_planned=True,
        self_approve=False,
        break_glass=False,
    )

    assert verdict["approved"] is True
    policy_input = cast(dict[str, Any], captured["payload"])
    assert policy_input["command_id"] == "promote-to-production"
    assert policy_input["requester_class"] == "human_operator"
    assert policy_input["contract"]["approval_policy"] == "operator_approved"
    assert policy_input["workflow"]["preferred_entrypoint"]["command"] == "make promote"
