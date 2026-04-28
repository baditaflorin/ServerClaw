"""Tests for ADR 0457 — host-pinning audit primitive.

Covers:
  1. `proxmox_guests[*].deployment_owner` schema validation (deployment loader).
  2. `_audit_topology()` flags drift when declared_owner != declaring deployment.
  3. `_audit_topology()` is silent when deployment_owner is absent.
  4. `_audit_topology()` is silent when declared_owner == declaring slug.
  5. `_audit_cross_deployment()` surfaces info-level pinning references.
  6. `--host` filter narrows to a single guest.
  7. CLI exit codes (0 clean, 1 drift, 2 usage/data).
  8. Schema rejects malformed deployment_owner slugs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "host_pinning_check.py"


def _load_module(repo_root_override: Path):
    spec = importlib.util.spec_from_file_location("host_pinning_for_ws0457", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["host_pinning_for_ws0457"] = module
    spec.loader.exec_module(module)
    module.REPO_ROOT = repo_root_override
    module.DEPLOYMENTS_DIR = repo_root_override / ".local" / "deployments"
    return module


@pytest.fixture
def synthetic_repo(tmp_path):
    (tmp_path / ".local" / "deployments").mkdir(parents=True)
    return tmp_path


def _write_topology(deployments_dir: Path, slug: str, guests: list[dict]) -> None:
    import yaml

    root = deployments_dir / slug
    root.mkdir(parents=True, exist_ok=True)
    (root / "topology.yml").write_text(yaml.safe_dump({"proxmox_guests": guests}, sort_keys=False))


# --- _audit_topology -------------------------------------------------------


def test_audit_topology_silent_when_owner_absent(synthetic_repo):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "nginx", "vmid": 110, "ipv4": "10.10.10.10"}],
    )
    issues = mod._audit_topology("alpha")
    assert issues == []


def test_audit_topology_silent_when_owner_matches(synthetic_repo):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "nginx", "vmid": 110, "ipv4": "10.10.10.10", "deployment_owner": "alpha"}],
    )
    issues = mod._audit_topology("alpha")
    assert issues == []


def test_audit_topology_flags_drift(synthetic_repo):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "nginx", "vmid": 110, "ipv4": "10.10.10.10", "deployment_owner": "beta"}],
    )
    issues = mod._audit_topology("alpha")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].declared_owner == "beta"
    assert issues[0].guest_name == "nginx"


def test_audit_topology_host_filter(synthetic_repo):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [
            {"name": "nginx", "vmid": 110, "ipv4": "10.10.10.10", "deployment_owner": "beta"},
            {"name": "postgres", "vmid": 160, "ipv4": "10.10.10.60", "deployment_owner": "gamma"},
        ],
    )
    nginx_issues = mod._audit_topology("alpha", host_filter="nginx")
    assert len(nginx_issues) == 1
    assert nginx_issues[0].guest_name == "nginx"


# --- _audit_cross_deployment ----------------------------------------------


def test_audit_cross_deployment_surfaces_info(synthetic_repo):
    """When sibling deployment beta declares a guest with
    deployment_owner=alpha, audit_cross from alpha's perspective should
    surface that as info."""
    mod = _load_module(synthetic_repo)
    _write_topology(mod.DEPLOYMENTS_DIR, "alpha", [{"name": "x", "vmid": 100, "ipv4": "10.0.0.1"}])
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "beta",
        [{"name": "shared", "vmid": 200, "ipv4": "10.0.0.2", "deployment_owner": "alpha"}],
    )
    issues = mod._audit_cross_deployment("alpha")
    info_issues = [i for i in issues if i.severity == "info"]
    assert len(info_issues) == 1
    assert info_issues[0].deployment == "beta"
    assert info_issues[0].guest_name == "shared"


# --- _audit_all ------------------------------------------------------------


def test_audit_all_walks_every_deployment(synthetic_repo):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "g1", "vmid": 100, "ipv4": "10.0.0.1", "deployment_owner": "wrong"}],
    )
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "beta",
        [{"name": "g2", "vmid": 200, "ipv4": "10.0.0.2", "deployment_owner": "also_wrong"}],
    )
    issues = mod._audit_all()
    assert len(issues) == 2
    assert {i.deployment for i in issues} == {"alpha", "beta"}


# --- CLI exit codes --------------------------------------------------------


def test_cli_exit_zero_when_clean(synthetic_repo, capsys):
    mod = _load_module(synthetic_repo)
    _write_topology(mod.DEPLOYMENTS_DIR, "alpha", [{"name": "x", "vmid": 100, "ipv4": "10.0.0.1"}])
    rc = mod.main(["--deployment", "alpha"])
    assert rc == 0


def test_cli_exit_one_on_drift(synthetic_repo, capsys):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "x", "vmid": 100, "ipv4": "10.0.0.1", "deployment_owner": "beta"}],
    )
    rc = mod.main(["--deployment", "alpha"])
    assert rc == 1


def test_cli_exit_two_when_no_active(synthetic_repo, monkeypatch, capsys):
    mod = _load_module(synthetic_repo)
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    rc = mod.main([])
    assert rc == 2


def test_cli_json_output_format(synthetic_repo, capsys):
    mod = _load_module(synthetic_repo)
    _write_topology(
        mod.DEPLOYMENTS_DIR,
        "alpha",
        [{"name": "x", "vmid": 100, "ipv4": "10.0.0.1", "deployment_owner": "beta"}],
    )
    rc = mod.main(["--deployment", "alpha", "--json"])
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert payload[0]["declared_owner"] == "beta"
    assert payload[0]["severity"] == "error"


# --- Schema validation -----------------------------------------------------


def test_topology_schema_accepts_deployment_owner_field():
    """The committed topology schema must accept the new field — otherwise
    the deployment loader rejects valid topologies after this ADR lands."""
    schema_path = REPO_ROOT / "config" / "contracts" / "deployment-v1" / "topology.schema.json"
    schema = json.loads(schema_path.read_text())
    guest_schema = schema["properties"]["proxmox_guests"]["items"]
    assert "deployment_owner" in guest_schema["properties"]
    assert guest_schema["properties"]["deployment_owner"]["type"] == "string"


def test_topology_schema_rejects_malformed_slug():
    """A slug starting with a hyphen or containing capitals violates
    `^[a-z0-9][a-z0-9_-]*$`. Lock that pattern in."""
    pytest.importorskip("jsonschema")
    from jsonschema import Draft202012Validator

    schema_path = REPO_ROOT / "config" / "contracts" / "deployment-v1" / "topology.schema.json"
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)
    bad_topology = {
        "proxmox_guests": [
            {"name": "x", "vmid": 100, "ipv4": "10.0.0.1", "deployment_owner": "-bad"},
        ]
    }
    errors = list(validator.iter_errors(bad_topology))
    assert any("deployment_owner" in str(e.absolute_path) for e in errors)
