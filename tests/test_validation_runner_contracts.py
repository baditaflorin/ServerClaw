from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "validation_runner_contracts.py"


def load_module(name: str = "validation_runner_contracts"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/validation-runner-contracts.schema.json",
                "schema_version": "1.0.0",
                "lanes": {
                    "alpha": {
                        "description": "alpha lane",
                        "requires_container_runtime": True,
                        "required_tools": ["docker", "python3"],
                        "allowed_network_reachability_classes": ["controller_local"],
                        "allowed_cpu_architectures": ["arm64", "x86_64"],
                        "require_scratch_cleanup_guarantee": True,
                    }
                },
                "runners": {
                    "test-runner": {
                        "description": "test runner",
                        "execution_surface": "controller_local",
                        "cpu_architectures": ["arm64", "x86_64"],
                        "emulation_support": [],
                        "container_runtime": {"engine": "docker", "supported": True},
                        "required_tools": ["docker", "python3"],
                        "network_reachability_class": "controller_local",
                        "scratch_cleanup_guarantee": "temp workspace",
                        "supported_validation_lanes": ["alpha"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_build_runner_context_records_lane_eligibility(tmp_path: Path, monkeypatch) -> None:
    module = load_module("validation_runner_contracts_context")
    catalog_path = tmp_path / "validation-runner-contracts.json"
    write_catalog(catalog_path)
    catalog = module.load_contract_catalog(catalog_path)

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        if command[0].endswith("docker") and command[1:3] == ["info", "--format"]:
            return module.subprocess.CompletedProcess(command, 0, stdout="26.1.0\n", stderr="")
        return module.subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} version\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.socket, "gethostname", lambda: "runner-host")
    monkeypatch.setattr(module.pyplatform, "machine", lambda: "arm64")

    payload = module.build_runner_context(catalog, runner_id="test-runner", workspace=tmp_path, lanes=["alpha"])

    assert payload["id"] == "test-runner"
    assert payload["environment_attestation"]["container_runtime"]["server_reachable"] is True
    assert payload["lane_evaluations"]["alpha"]["eligible"] is True


def test_build_runner_context_honors_runtime_binary_override(tmp_path: Path, monkeypatch) -> None:
    module = load_module("validation_runner_contracts_runtime_override")
    catalog_path = tmp_path / "validation-runner-contracts.json"
    write_catalog(catalog_path)
    catalog = module.load_contract_catalog(catalog_path)
    fake_docker = tmp_path / "fake-docker"
    fake_docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_docker.chmod(0o755)

    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: None if name == "docker" else f"/usr/bin/{name}",
    )

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        return module.subprocess.CompletedProcess(command, 0, stdout="26.1.0\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.build_runner_context(
        catalog,
        runner_id="test-runner",
        workspace=tmp_path,
        lanes=["alpha"],
        container_runtime_binary=str(fake_docker),
    )

    assert payload["environment_attestation"]["container_runtime"]["path"] == str(fake_docker.resolve())
    assert payload["environment_attestation"]["tooling"]["docker"]["path"] == str(fake_docker.resolve())
    assert payload["lane_evaluations"]["alpha"]["eligible"] is True


def test_evaluate_lane_eligibility_reports_missing_runtime(tmp_path: Path) -> None:
    module = load_module("validation_runner_contracts_missing_runtime")
    catalog_path = tmp_path / "validation-runner-contracts.json"
    write_catalog(catalog_path)
    catalog = module.load_contract_catalog(catalog_path)

    attestation = {
        "cpu_architecture": "x86_64",
        "container_runtime": {"available": False, "server_reachable": False, "error": "docker missing"},
        "tooling": {
            "docker": {"available": False},
            "python3": {"available": True},
        },
        "network_reachability_class": "controller_local",
        "scratch_space": {"exists": True, "cleanup_guarantee": "temp workspace"},
    }

    result = module.evaluate_lane_eligibility(
        catalog,
        runner_id="test-runner",
        lane_id="alpha",
        attestation=attestation,
    )

    assert result.eligible is False
    assert any("docker" in reason for reason in result.reasons)


def test_repo_catalog_covers_current_gate_and_build_server_contracts(monkeypatch) -> None:
    module = load_module("validation_runner_contracts_repo_catalog")
    catalog = module.load_contract_catalog()
    monkeypatch.setattr(module, "_validate_schema", lambda _catalog: None)

    module.validate_contract_catalog(catalog)


def test_validate_contract_catalog_rejects_absolute_repo_local_build_server_key(monkeypatch) -> None:
    module = load_module("validation_runner_contracts_absolute_build_server_key")
    catalog = module.load_contract_catalog()
    build_server_config = {
        "ssh_key": "/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519",
        "ssh_options": [],
        "commands": {},
    }

    monkeypatch.setattr(module, "_validate_schema", lambda _catalog: None)
    monkeypatch.setattr(module, "_load_validation_gate", lambda: {})

    with pytest.raises(ValueError, match="must not embed an operator workstation path"):
        module.validate_contract_catalog(catalog, build_server_config=build_server_config)


def test_validate_contract_catalog_rejects_legacy_build_server_key_name(monkeypatch) -> None:
    module = load_module("validation_runner_contracts_legacy_build_server_key_name")
    catalog = module.load_contract_catalog()
    build_server_config = {
        "ssh_key": ".local/ssh/bootstrap.id_ed25519",
        "ssh_options": ["-o", "ProxyCommand=ssh -i .local/ssh/hetzner_llm_agents_ed25519 -W %h:%p jump"],
        "commands": {},
    }

    monkeypatch.setattr(module, "_validate_schema", lambda _catalog: None)
    monkeypatch.setattr(module, "_load_validation_gate", lambda: {})

    with pytest.raises(ValueError, match="legacy deployment-specific bootstrap key name"):
        module.validate_contract_catalog(catalog, build_server_config=build_server_config)
