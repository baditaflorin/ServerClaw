from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import preflight_controller_local as preflight
import workflow_catalog


def minimal_secret_manifest(secret_path: Path) -> dict:
    return {
        "secrets": {
            "bootstrap_ssh_private_key": {
                "kind": "file",
                "path": str(secret_path),
                "status": "active",
            }
        }
    }


def minimal_workflow(*, workflow_id: str, preflight_payload: dict) -> dict:
    return {
        "workflows": {
            workflow_id: {
                "description": f"{workflow_id} test workflow",
                "lifecycle_status": "active",
                "preferred_entrypoint": {
                    "kind": "make_target",
                    "target": "validate",
                    "command": "make validate",
                },
                "preflight": preflight_payload,
                "validation_targets": [],
                "live_impact": "repo_only",
                "owner_runbook": "docs/runbooks/controller-local-secrets-and-preflight.md",
                "implementation_refs": [
                    "Makefile",
                    "scripts/preflight_controller_local.py",
                ],
                "outputs": [
                    "Test output",
                ],
                "verification_commands": [
                    "make validate",
                ],
                "execution_class": "mutation",
            }
        }
    }


def test_validate_workflow_catalog_rejects_unknown_bootstrap_manifest(tmp_path: Path) -> None:
    key_path = tmp_path / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")

    secret_manifest = minimal_secret_manifest(key_path)
    catalog = minimal_workflow(
        workflow_id="demo",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "bootstrap_manifest_ids": ["missing-manifest"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "controller-local-base": {
                "description": "Base bootstrap",
                "optional_read_only_caches": [],
            }
        },
    }

    with pytest.raises(ValueError, match="unknown bootstrap manifest"):
        workflow_catalog.validate_workflow_catalog(catalog, secret_manifest, bootstrap_catalog)


def test_validate_workflow_catalog_rejects_invalid_health_check(tmp_path: Path) -> None:
    key_path = tmp_path / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")

    secret_manifest = minimal_secret_manifest(key_path)
    catalog = minimal_workflow(
        workflow_id="demo",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "health_checks": [
                {
                    "id": "missing-command",
                    "description": "Broken health check",
                }
            ],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "controller-local-base": {
                "description": "Base bootstrap",
                "optional_read_only_caches": [],
            }
        },
    }

    with pytest.raises(ValueError, match="preflight.health_checks\\[0\\]\\.command"):
        workflow_catalog.validate_workflow_catalog(catalog, secret_manifest, bootstrap_catalog)


def test_run_workflow_materializes_missing_generated_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path
    key_path = repo_root / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(key_path)
    workflow = minimal_workflow(
        workflow_id="configure-edge-publication",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "bootstrap_manifest_ids": ["shared-edge-generated-portals"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "shared-edge-generated-portals": {
                "description": "Generate required portals",
                "generated_artifacts": [
                    {
                        "id": "docs_portal",
                        "kind": "directory",
                        "path": "build/docs-portal",
                        "materialize_command": "mkdir -p build/docs-portal",
                        "description": "Docs portal directory",
                    }
                ],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "configure-edge-publication",
    )

    assert exit_code == 0
    assert (repo_root / "build" / "docs-portal").is_dir()


def test_run_workflow_materialize_command_uses_current_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    key_path = repo_root / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")
    helper_dir = repo_root / "test-bin"
    helper_dir.mkdir()
    helper = helper_dir / "materialize-docs-portal"
    helper.write_text(
        "#!/bin/sh\nmkdir -p build/docs-portal\n",
        encoding="utf-8",
    )
    helper.chmod(0o755)
    secret_manifest = minimal_secret_manifest(key_path)
    workflow = minimal_workflow(
        workflow_id="live-apply-service",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "bootstrap_manifest_ids": ["shared-edge-generated-portals"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "shared-edge-generated-portals": {
                "description": "Generate required portals",
                "generated_artifacts": [
                    {
                        "id": "docs_portal",
                        "kind": "directory",
                        "path": "build/docs-portal",
                        "materialize_command": "materialize-docs-portal",
                        "description": "Docs portal directory",
                    }
                ],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)
    monkeypatch.setenv("PATH", f"{helper_dir}{os.pathsep}{os.environ['PATH']}")

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "live-apply-service",
    )

    assert exit_code == 0
    assert (repo_root / "build" / "docs-portal").is_dir()


def test_run_workflow_fails_when_required_bootstrap_input_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    key_path = repo_root / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(key_path)
    workflow = minimal_workflow(
        workflow_id="configure-edge-publication",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "bootstrap_manifest_ids": ["required-local-inputs"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "required-local-inputs": {
                "description": "Require one local helper path",
                "required_local_inputs": [
                    {
                        "id": "step_ca_root_certificate",
                        "kind": "file",
                        "path": ".local/step-ca/certs/root_ca.crt",
                        "description": "Step CA root",
                    }
                ],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "configure-edge-publication",
    )

    assert exit_code == 1


def test_run_workflow_resolves_repo_local_secret_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path
    mirrored_key = repo_root / ".local" / "ssh" / "id_ed25519"
    mirrored_key.parent.mkdir(parents=True)
    mirrored_key.write_text("key", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(
        Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/id_ed25519")
    )
    workflow = minimal_workflow(
        workflow_id="live-apply-service",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {},
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "live-apply-service",
    )

    assert exit_code == 0


def test_run_workflow_executes_health_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path
    key_path = repo_root / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(key_path)
    workflow = minimal_workflow(
        workflow_id="operator-onboard",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "health_checks": [
                {
                    "id": "demo-health",
                    "description": "Demo health check passes",
                    "command": "printf 'healthy\\n'",
                    "timeout_seconds": 2,
                }
            ],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "controller-local-base": {
                "description": "Base bootstrap",
                "optional_read_only_caches": [],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "operator-onboard",
    )

    assert exit_code == 0


def test_run_workflow_materializes_shared_bootstrap_aliases_for_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0333-live-apply"
    shared_ssh_dir = repo_root / ".local" / "ssh"
    worktree_root.mkdir(parents=True)
    shared_ssh_dir.mkdir(parents=True)
    (shared_ssh_dir / "hetzner_llm_agents_ed25519").write_text("PRIVATE\n", encoding="utf-8")
    (shared_ssh_dir / "hetzner_llm_agents_ed25519.pub").write_text("PUBLIC\n", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(
        Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/bootstrap.id_ed25519")
    )
    workflow = minimal_workflow(
        workflow_id="post-merge-gate",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "bootstrap_manifest_ids": ["controller-local-base"],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "controller-local-base": {
                "description": "Base bootstrap",
                "generated_artifacts": [
                    {
                        "id": "bootstrap_private_key_alias",
                        "kind": "file",
                        "path": ".local/ssh/bootstrap.id_ed25519",
                        "resolve_repo_local": True,
                        "materialize_command": (
                            f"python3 {REPO_ROOT / 'scripts' / 'materialize_bootstrap_key_alias.py'} "
                            f"--repo-root {repo_root}"
                        ),
                        "description": "Bootstrap private key alias",
                    },
                    {
                        "id": "bootstrap_public_key_alias",
                        "kind": "file",
                        "path": ".local/ssh/bootstrap.id_ed25519.pub",
                        "resolve_repo_local": True,
                        "materialize_command": (
                            f"python3 {REPO_ROOT / 'scripts' / 'materialize_bootstrap_key_alias.py'} "
                            f"--repo-root {repo_root}"
                        ),
                        "description": "Bootstrap public key alias",
                    },
                ],
                "optional_read_only_caches": [],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", worktree_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "post-merge-gate",
    )

    assert exit_code == 0
    assert (shared_ssh_dir / "bootstrap.id_ed25519").is_symlink()
    assert (shared_ssh_dir / "bootstrap.id_ed25519.pub").is_symlink()


def test_run_workflow_fails_when_health_check_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path
    key_path = repo_root / ".local" / "ssh" / "id_ed25519"
    key_path.parent.mkdir(parents=True)
    key_path.write_text("key", encoding="utf-8")
    secret_manifest = minimal_secret_manifest(key_path)
    workflow = minimal_workflow(
        workflow_id="operator-onboard",
        preflight_payload={
            "required": True,
            "required_secret_ids": ["bootstrap_ssh_private_key"],
            "health_checks": [
                {
                    "id": "demo-health",
                    "description": "Demo health check fails",
                    "command": "exit 7",
                    "timeout_seconds": 2,
                }
            ],
        },
    )
    bootstrap_catalog = {
        "schema_version": "1.0.0",
        "manifests": {
            "controller-local-base": {
                "description": "Base bootstrap",
                "optional_read_only_caches": [],
            }
        },
    }

    monkeypatch.setattr(preflight, "REPO_ROOT", repo_root)

    exit_code = preflight.run_workflow(
        secret_manifest,
        workflow,
        bootstrap_catalog,
        "operator-onboard",
    )

    assert exit_code == 1
