from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RENOVATE_CONFIG_PATH = REPO_ROOT / "renovate.json"
RENOVATE_WORKFLOW_PATH = REPO_ROOT / ".gitea" / "workflows" / "renovate.yml"
VALIDATE_MODULE_PATH = REPO_ROOT / "scripts" / "validate_renovate_contract.py"
TOKEN_MODULE_PATH = REPO_ROOT / "scripts" / "renovate_runtime_token.py"
GUARD_MODULE_PATH = REPO_ROOT / "scripts" / "renovate_stack_digest_guard.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_renovate_config_targets_gitea_and_custom_repo_surfaces() -> None:
    config = json.loads(RENOVATE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["platform"] == "gitea"
    assert config["dependencyDashboard"] is True
    assert config["automerge"] is False
    assert config["platformAutomerge"] is False
    assert any("image-catalog" in "".join(manager["managerFilePatterns"]) for manager in config["customManagers"])
    assert any("versions" in "".join(manager["managerFilePatterns"]) and "stack" in "".join(manager["managerFilePatterns"]) for manager in config["customManagers"])


def test_renovate_workflow_uses_harbor_pinned_image_and_runtime_token_helper() -> None:
    workflow = RENOVATE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "registry.lv3.org/check-runner/renovate:" in workflow
    assert "@sha256:" in workflow
    assert "ghcr.io/renovatebot/renovate" not in workflow
    assert "scripts/renovate_runtime_token.py create" in workflow
    assert "scripts/renovate_runtime_token.py cleanup" in workflow
    assert 'workspace_host_path="${PWD/#\\/data/${GITEA_RUNNER_HOST_DATA_DIR}}"' in workflow


def test_validate_renovate_contract_passes_for_repo_files() -> None:
    module = load_module(VALIDATE_MODULE_PATH, "validate_renovate_contract")
    assert module.main() == 0


def test_renovate_runtime_token_writes_runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module(TOKEN_MODULE_PATH, "renovate_runtime_token_test")
    state_file = tmp_path / "renovate-token.json"
    env_file = tmp_path / "renovate.env"

    monkeypatch.setenv("RENOVATE_GITEA_BASE_URL", "http://10.10.10.20:3003")
    monkeypatch.setenv("RENOVATE_GITEA_USERNAME", "renovate-bot")
    monkeypatch.setenv("RENOVATE_GITEA_PASSWORD", "secret")
    monkeypatch.setenv("RENOVATE_GITEA_TOKEN_SCOPES", "write:repository,read:user")
    monkeypatch.setenv("RENOVATE_REPOSITORY", "ops/proxmox_florin_server")

    def fake_request_json(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["method"] == "POST"
        assert kwargs["expected_status"] == 201
        return {"id": 123, "name": "renovate-test", "sha1": "token-value"}

    monkeypatch.setattr(module, "request_json", fake_request_json)
    monkeypatch.setattr(module.time, "strftime", lambda fmt, *args: "20260330T120000Z")

    module.create_runtime_token(state_file=state_file, env_file=env_file)

    assert json.loads(state_file.read_text(encoding="utf-8"))["token_id"] == "123"
    env_payload = env_file.read_text(encoding="utf-8")
    assert "RENOVATE_PLATFORM=gitea" in env_payload
    assert "RENOVATE_ENDPOINT=http://10.10.10.20:3003/api/v1/" in env_payload
    assert "RENOVATE_REPOSITORIES=ops/proxmox_florin_server" in env_payload
    assert "RENOVATE_TOKEN=token-value" in env_payload


def test_renovate_stack_digest_guard_flags_missing_catalog_update(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module(GUARD_MODULE_PATH, "renovate_stack_digest_guard_test")
    stack_path = tmp_path / "versions" / "stack.yaml"
    image_catalog_path = tmp_path / "config" / "image-catalog.json"
    stack_path.parent.mkdir(parents=True)
    image_catalog_path.parent.mkdir(parents=True)
    stack_path.write_text(
        "ollama:\n  api_version: 0.18.3\n",
        encoding="utf-8",
    )
    image_catalog_path.write_text(
        json.dumps(
            {
                "images": {
                    "ollama_runtime": {
                        "ref": "docker.io/ollama/ollama:0.18.2@sha256:current"
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "STACK_PATH", stack_path)
    monkeypatch.setattr(module, "IMAGE_CATALOG_PATH", image_catalog_path)
    monkeypatch.setattr(
        module,
        "load_git_object",
        lambda ref, relative_path: (
            "ollama:\n  api_version: 0.18.2\n"
            if relative_path == "versions/stack.yaml"
            else json.dumps({"images": {"ollama_runtime": {"ref": "docker.io/ollama/ollama:0.18.2@sha256:base"}}})
        ),
    )

    with pytest.raises(ValueError, match="config/image-catalog.json"):
        module.validate_against_base("origin/main")
