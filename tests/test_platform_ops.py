from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "platform_ops.py"


def load_module(name: str = "platform_ops"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def gate_ids(plan: dict) -> set[str]:
    return {item["gate"] for item in plan["validation_gates"]}


def test_validation_plan_maps_runtime_role_changes_to_ansible_and_service_gates() -> None:
    module = load_module("platform_ops_role_plan")

    plan = module.cmd_validation_plan(
        argparse.Namespace(
            since=None,
            changed_files=[
                "collections/ansible_collections/lv3/platform/roles/directus_runtime/defaults/main.yml",
            ],
        )
    )

    gates = gate_ids(plan)
    assert {"yaml", "ansible-syntax", "ansible-lint", "role-argument-specs", "service-completeness"} <= gates
    assert "./scripts/validate_repo.sh ansible-syntax" in plan["commands"]
    assert "python3 scripts/validate_service_completeness.py --validate" in plan["commands"]
    assert plan["unmapped_files"] == []


def test_validation_plan_maps_adr_and_workstream_changes_to_agent_contracts() -> None:
    module = load_module("platform_ops_docs_plan")

    plan = module.cmd_validation_plan(
        argparse.Namespace(
            since=None,
            changed_files=[
                "docs/adr/0391-cpu-only-operational-automation.md",
                "workstreams/active/ws-0391-live-apply.yaml",
            ],
        )
    )

    gates = gate_ids(plan)
    assert {"agent-standards", "documentation-index", "generated-docs", "workstream-surfaces", "yaml"} <= gates
    assert "uv run --with pyyaml python3 scripts/generate_adr_index.py --check" in plan["commands"]
    assert "./scripts/validate_repo.sh workstream-surfaces" in plan["commands"]


def test_validation_plan_maps_live_apply_evidence() -> None:
    module = load_module("platform_ops_evidence_plan")

    plan = module.cmd_validation_plan(
        argparse.Namespace(
            since=None,
            changed_files=[
                "receipts/live-applies/evidence/2026-04-21-ws-0391-live-apply-cli-and-validation-r1-0.178.148.txt",
            ],
        )
    )

    assert "live-apply-receipts" in gate_ids(plan)
    assert "python3 scripts/live_apply_receipts.py --validate" in plan["commands"]
    assert plan["unmapped_files"] == []


def test_validation_plan_subcommand_emits_json(capsys) -> None:
    module = load_module("platform_ops_main_plan")

    rc = module.main(["validation-plan", "--changed-files", "scripts/platform_ops.py"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert "validation_gates" in payload
    assert "python-type-safety" in gate_ids(payload)


def test_makefile_exposes_adr_0391_ops_targets() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "ops-impact:",
        "ops-converge-plan:",
        "ops-completeness:",
        "ops-validation-plan:",
        "ops-references:",
        "ops-changelog:",
    ):
        assert target in makefile
