from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

import platform.interface_contracts as interface_contracts
from platform.interface_contracts import check_live_apply_target, validate_contracts


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "interface_contracts.py"


def load_interface_contracts_module():
    spec = importlib.util.spec_from_file_location("interface_contracts", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_workstream_registry_contract_validates() -> None:
    contracts = validate_contracts()
    assert any(contract["contract_id"] == "workstream-registry-v1" for contract in contracts)


def test_workstream_registry_contract_accepts_in_progress_status(tmp_path: Path, monkeypatch) -> None:
    workstreams_path = tmp_path / "workstreams.yaml"
    workstreams_path.write_text(
        (REPO_ROOT / "workstreams.yaml")
        .read_text(encoding="utf-8")
        .replace("status: merged", "status: in_progress", 1),
        encoding="utf-8",
    )

    monkeypatch.setattr(interface_contracts, "WORKSTREAMS_PATH", workstreams_path)

    contracts = interface_contracts.validate_contracts()

    assert any(contract["contract_id"] == "workstream-registry-v1" for contract in contracts)


def test_workstream_registry_contract_accepts_ready_for_merge_status(tmp_path: Path, monkeypatch) -> None:
    workstreams_path = tmp_path / "workstreams.yaml"
    workstreams_path.write_text(
        (REPO_ROOT / "workstreams.yaml")
        .read_text(encoding="utf-8")
        .replace("status: merged", "status: ready_for_merge", 1),
        encoding="utf-8",
    )

    monkeypatch.setattr(interface_contracts, "WORKSTREAMS_PATH", workstreams_path)

    contracts = interface_contracts.validate_contracts()

    assert any(contract["contract_id"] == "workstream-registry-v1" for contract in contracts)


def test_converge_workflow_contract_validates() -> None:
    contracts = validate_contracts()
    assert any(contract["contract_id"] == "converge-workflow-live-apply-v1" for contract in contracts)


def test_script_list_reports_new_contracts(capsys) -> None:
    module = load_interface_contracts_module()
    exit_code = module.main(["--list"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "workstream-registry-v1" in captured.out
    assert "converge-workflow-live-apply-v1" in captured.out


def test_check_live_apply_target_accepts_known_service() -> None:
    result = check_live_apply_target("service:n8n")
    assert result["playbook"].endswith("/playbooks/services/n8n.yml")


def test_check_live_apply_target_accepts_nextcloud_service() -> None:
    result = check_live_apply_target("service:nextcloud")
    assert result["playbook"].endswith("/playbooks/services/nextcloud.yml")


def test_check_live_apply_target_accepts_group() -> None:
    result = check_live_apply_target("group:automation")
    assert result["playbook"].endswith("/playbooks/groups/automation.yml")


def test_makefile_routes_live_apply_through_contract_check() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert 'scripts/interface_contracts.py --check-live-apply "service:$(service)"' in makefile
    assert 'scripts/interface_contracts.py --check-live-apply "group:$(group)"' in makefile
    assert 'scripts/interface_contracts.py --check-live-apply "site:site"' in makefile
