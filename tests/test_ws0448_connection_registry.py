"""Tests for ADR 0448 — per-deployment connection registry + wrapper.

Covers the three pieces shipped together:

1. `Deployment.connection` is loaded from `connection.yml` when present
   and is `None` when absent (existing deployments without the file
   continue to work).
2. The connection schema rejects malformed payloads.
3. `_connection_env_block()` produces the `LV3_PROXMOX_HOST_*` /
   `LV3_BOOTSTRAP_SSH_PRIVATE_KEY` / `PLATFORM_IDENTITY_OVERLAY`
   variables documented in ADR 0448.
4. `_resolve_ssh_key()` handles relative + absolute paths.

The tests reuse the same `_load_deployment_module(repo_root_override)`
trick the ws-0445 integration test uses so we can point the loader at a
synthetic `.local/deployments/` tree under `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_SCRIPT = REPO_ROOT / "scripts" / "deployment.py"


def _load_deployment_module(repo_root_override: Path):
    spec = importlib.util.spec_from_file_location("deployment_for_ws0448", DEPLOYMENT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["deployment_for_ws0448"] = module
    spec.loader.exec_module(module)
    module.REPO_ROOT = repo_root_override
    module.DEPLOYMENTS_DIR = repo_root_override / ".local" / "deployments"
    module.ACTIVE_FILE = repo_root_override / ".local" / "active-deployment"
    module.DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    # SCHEMA_DIR is computed at import time from REPO_ROOT, which
    # _find_main_repo_root() resolves to the parent main checkout —
    # not this worktree. Pin it back at this worktree's schemas so the
    # tests run against the schemas under review, not the parent's.
    module.SCHEMA_DIR = REPO_ROOT / "config" / "contracts" / "deployment-v1"
    return module


def _write_deployment(
    deploy_root: Path,
    slug: str,
    *,
    identity: dict[str, Any] | None = None,
    topology: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    connection: dict[str, Any] | None = None,
) -> Path:
    root = deploy_root / slug
    root.mkdir(parents=True, exist_ok=True)
    if identity is not None:
        (root / "identity.yml").write_text(yaml.safe_dump(identity, sort_keys=False))
    if topology is not None:
        (root / "topology.yml").write_text(yaml.safe_dump(topology, sort_keys=False))
    if profile is not None:
        (root / "profile.yml").write_text(yaml.safe_dump(profile, sort_keys=False))
    if connection is not None:
        (root / "connection.yml").write_text(yaml.safe_dump(connection, sort_keys=False))
    return root


def _valid_identity() -> dict[str, Any]:
    return {
        "platform_domain": "example.invalid",
        "platform_operator_email": "ops@example.invalid",
        "platform_operator_name": "Example Operator",
    }


def _valid_topology() -> dict[str, Any]:
    return {"proxmox_guests": [{"name": "fixture-guest", "vmid": 199, "ipv4": "10.10.10.199"}]}


def _valid_connection() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "proxmox_host": {
            "addr": "203.0.113.10",
            "port": 2222,
            "user": "ops",
            "key": "bootstrap.id_ed25519",
        },
        "guest_ssh": {
            "user": "ops",
            "key": "bootstrap.id_ed25519",
            "jump_via": "proxmox_host",
        },
    }


@pytest.fixture
def synthetic_repo_root(tmp_path):
    (tmp_path / ".local" / "deployments").mkdir(parents=True)
    (tmp_path / ".local" / "ssh").mkdir(parents=True)
    return tmp_path


def test_connection_field_absent_when_file_missing(synthetic_repo_root):
    """Deployments shipped before ADR 0448 must keep loading."""
    mod = _load_deployment_module(synthetic_repo_root)
    _write_deployment(
        mod.DEPLOYMENTS_DIR,
        "no_conn",
        identity=_valid_identity(),
        topology=_valid_topology(),
        profile={"profiles": ["core"]},
    )
    loaded = mod.load("no_conn", validate=True)
    assert loaded.connection is None


def test_connection_field_loaded_when_file_present(synthetic_repo_root):
    mod = _load_deployment_module(synthetic_repo_root)
    _write_deployment(
        mod.DEPLOYMENTS_DIR,
        "with_conn",
        identity=_valid_identity(),
        topology=_valid_topology(),
        profile={"profiles": ["core"]},
        connection=_valid_connection(),
    )
    loaded = mod.load("with_conn", validate=True)
    assert loaded.connection is not None
    assert loaded.connection["proxmox_host"]["addr"] == "203.0.113.10"


def test_connection_schema_rejects_malformed_payload(synthetic_repo_root):
    """A connection.yml that violates the schema must fail validation."""
    pytest.importorskip("jsonschema")
    mod = _load_deployment_module(synthetic_repo_root)
    bad = _valid_connection()
    del bad["proxmox_host"]  # required field
    _write_deployment(
        mod.DEPLOYMENTS_DIR,
        "bad_conn",
        identity=_valid_identity(),
        topology=_valid_topology(),
        profile={"profiles": ["core"]},
        connection=bad,
    )
    with pytest.raises(mod.DeploymentValidationError):
        mod.load("bad_conn", validate=True)


def test_env_block_emits_documented_variables(synthetic_repo_root):
    mod = _load_deployment_module(synthetic_repo_root)
    _write_deployment(
        mod.DEPLOYMENTS_DIR,
        "envtest",
        identity=_valid_identity(),
        topology=_valid_topology(),
        profile={"profiles": ["core"]},
        connection=_valid_connection(),
    )
    loaded = mod.load("envtest", validate=True)
    env = mod._connection_env_block(loaded)

    assert env["LV3_PROXMOX_HOST_ADDR"] == "203.0.113.10"
    assert env["LV3_PROXMOX_HOST_PORT"] == "2222"
    assert env["LV3_PROXMOX_HOST_USER"] == "ops"
    assert env["LV3_GUEST_SSH_USER"] == "ops"
    # Relative SSH-key path resolves under .local/ssh/
    assert env["LV3_BOOTSTRAP_SSH_PRIVATE_KEY"].endswith(".local/ssh/bootstrap.id_ed25519")
    # PLATFORM_IDENTITY_OVERLAY points at the per-deployment identity.yml.
    assert env["PLATFORM_IDENTITY_OVERLAY"].endswith("envtest/identity.yml")


def test_env_block_empty_when_no_connection(synthetic_repo_root):
    mod = _load_deployment_module(synthetic_repo_root)
    _write_deployment(
        mod.DEPLOYMENTS_DIR,
        "no_conn2",
        identity=_valid_identity(),
        topology=_valid_topology(),
        profile={"profiles": ["core"]},
    )
    loaded = mod.load("no_conn2", validate=True)
    assert mod._connection_env_block(loaded) == {}


def test_resolve_ssh_key_handles_absolute_paths(synthetic_repo_root):
    mod = _load_deployment_module(synthetic_repo_root)
    abs_path = "/etc/ssh/ssh_host_ed25519_key"
    resolved = mod._resolve_ssh_key(abs_path, synthetic_repo_root)
    assert str(resolved) == abs_path


def test_resolve_ssh_key_resolves_relative_against_local_ssh(synthetic_repo_root):
    mod = _load_deployment_module(synthetic_repo_root)
    resolved = mod._resolve_ssh_key("foo/bar.key", synthetic_repo_root)
    expected = (synthetic_repo_root / ".local" / "ssh" / "foo" / "bar.key").resolve()
    assert resolved == expected
