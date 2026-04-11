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


def test_renovate_config_targets_main_and_custom_repo_surfaces() -> None:
    config = json.loads(RENOVATE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert "platform" not in config
    assert config["dependencyDashboard"] is True
    assert config["automerge"] is False
    assert config["platformAutomerge"] is False
    assert config["gitAuthor"] == "Renovate Bot <renovate-bot@lv3.internal>"
    assert config["baseBranchPatterns"] == ["main"]
    assert any("image-catalog" in "".join(manager["managerFilePatterns"]) for manager in config["customManagers"])
    assert any(
        "versions" in "".join(manager["managerFilePatterns"]) and "stack" in "".join(manager["managerFilePatterns"])
        for manager in config["customManagers"]
    )


def test_renovate_workflow_uses_harbor_pinned_image_and_runtime_token_helper() -> None:
    workflow = RENOVATE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "registry.example.com/check-runner/renovate:" in workflow
    assert "@sha256:" in workflow
    assert "ghcr.io/renovatebot/renovate" not in workflow
    assert "scripts/renovate_runtime_token.py create" in workflow
    assert "scripts/renovate_runtime_token.py cleanup" in workflow
    assert "Bootstrap Docker CLI and discover runner host paths" in workflow
    assert 'current_container_id="${HOSTNAME:-$(hostname)}"' in workflow
    assert "cgroup_container_id" in workflow
    assert "name=WORKFLOW-renovate_JOB-renovate" in workflow
    assert ".tmp/docker-bin.path" in workflow
    assert 'docker_bin="$(ensure_docker_bin)"' not in workflow
    assert workflow.count("ensure_docker_bin") >= 8
    assert workflow.count("resolve_docker_bin") >= 8
    assert "apt-get install -y --no-install-recommends docker-cli" in workflow
    assert "hash -r" in workflow
    assert 'test -d "${workspace_host_path}"' not in workflow
    assert 'test -s "${bootstrap_host_dir}/renovate.env"' not in workflow
    assert ".tmp/workspace-host.path" in workflow
    assert ".tmp/bootstrap-host.path" in workflow
    assert 'renovate_add_host_arg=""' in workflow
    assert "RENOVATE_GIT_CLONE_HOST:-" in workflow
    assert "RENOVATE_GIT_CLONE_HOST_ADDRESS:-" in workflow
    assert "RENOVATE_GIT_CLONE_HOST_PORT:-" in workflow
    assert "RENOVATE_GIT_CLONE_TARGET_HOST:-" in workflow
    assert "RENOVATE_GIT_CLONE_TARGET_PORT:-" in workflow
    assert "--add-host=${RENOVATE_GIT_CLONE_HOST}:${RENOVATE_GIT_CLONE_HOST_ADDRESS}" in workflow
    assert "cleanup_clone_proxy()" in workflow
    assert "ThreadedTCPServer" in workflow
    assert "Renovate clone relay did not become ready." in workflow
    assert "-e RENOVATE_GIT_AUTHOR \\" in workflow
    assert "-e RENOVATE_REQUIRE_CONFIG \\" in workflow
    assert "-e RENOVATE_ONBOARDING \\" in workflow
    assert "RENOVATE_X_STATIC_REPO_CONFIG_FILE=/workspace/renovate.json" in workflow
    assert '-v "${bootstrap_host_dir}:/var/run/lv3/renovate:ro"' in workflow
    assert "RENOVATE_HELPER_IMAGE: registry.example.com/check-runner/python:3.12.10@sha256:" in workflow


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
    monkeypatch.setenv("RENOVATE_REPOSITORY", "ops/proxmox-host_server")
    monkeypatch.setenv("RENOVATE_GIT_CLONE_HOST", "git.example.com")
    monkeypatch.setenv("RENOVATE_GIT_CLONE_HOST_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("RENOVATE_GIT_CLONE_HOST_PORT", "3009")
    monkeypatch.setenv("RENOVATE_GIT_CLONE_TARGET_HOST", "10.10.10.20")
    monkeypatch.setenv("RENOVATE_GIT_CLONE_TARGET_PORT", "3003")

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
    assert "RENOVATE_REPOSITORIES=ops/proxmox-host_server" in env_payload
    assert "RENOVATE_TOKEN=token-value" in env_payload
    assert "RENOVATE_GIT_AUTHOR='Renovate Bot <renovate-bot@lv3.internal>'" in env_payload
    assert "RENOVATE_REQUIRE_CONFIG=optional" in env_payload
    assert "RENOVATE_ONBOARDING=false" in env_payload
    assert "RENOVATE_GIT_CLONE_HOST=git.example.com" in env_payload
    assert "RENOVATE_GIT_CLONE_HOST_ADDRESS=127.0.0.1" in env_payload
    assert "RENOVATE_GIT_CLONE_HOST_PORT=3009" in env_payload
    assert "RENOVATE_GIT_CLONE_TARGET_HOST=10.10.10.20" in env_payload
    assert "RENOVATE_GIT_CLONE_TARGET_PORT=3003" in env_payload


def test_renovate_stack_digest_guard_flags_missing_catalog_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
        json.dumps({"images": {"ollama_runtime": {"ref": "docker.io/ollama/ollama:0.18.2@sha256:current"}}}),
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
