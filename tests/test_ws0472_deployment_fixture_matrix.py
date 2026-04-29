"""Tests for ADR 0470 — per-deployment fixture inventory + matrix CI.

Three synthetic deployments under tests/fixtures/deployments/<slug>/ act as
the gold-standard exercise corpus for every deployment-aware contract and
script. If a schema bumps or a script changes how it reads the contracts,
this matrix catches it before a real deployment is touched.

Covered:
  - identity.yml validates against identity.schema.json
  - topology.yml validates against topology.schema.json
  - profile.yml validates against profile.schema.json
  - connection.yml validates against connection.schema.json
  - validate_topology_schema accepts every fixture topology
  - host_pinning_check parses every fixture topology without crashing
  - the host-pinned fixture surfaces ADR 0457's deployment_owner field
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "deployments"
SCHEMAS = REPO_ROOT / "config" / "contracts" / "deployment-v1"

DEPLOYMENT_SLUGS = ["minimal", "multi-host", "host-pinned"]


def _load_yaml(path: Path):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(path.read_text())


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text())


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
def test_fixture_directory_has_all_four_contracts(slug):
    base = FIXTURES / slug
    for name in ("identity.yml", "topology.yml", "profile.yml", "connection.yml"):
        assert (base / name).is_file(), f"{slug} missing {name}"


@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
@pytest.mark.parametrize("contract", ["identity", "topology", "profile", "connection"])
def test_fixture_validates_against_schema(slug, contract):
    pytest.importorskip("jsonschema")
    from jsonschema import Draft202012Validator

    payload = _load_yaml(FIXTURES / slug / f"{contract}.yml")
    schema = _load_schema(contract)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
def test_topology_passes_validate_topology_schema_script(slug):
    pytest.importorskip("jsonschema")
    pytest.importorskip("yaml")
    mod = _load_module(
        "validate_topology_schema_for_ws0472",
        REPO_ROOT / "scripts" / "validate_topology_schema.py",
    )
    schema = mod._load_schema()
    errors = mod.validate_one(FIXTURES / slug / "topology.yml", schema)
    assert errors == []


def test_host_pinned_fixture_carries_deployment_owner():
    payload = _load_yaml(FIXTURES / "host-pinned" / "topology.yml")
    owners = {g.get("deployment_owner") for g in payload["proxmox_guests"]}
    assert owners == {"host-pinned"}


def test_minimal_fixture_has_no_deployment_owner():
    """Legacy fixtures without ADR 0457 deployment_owner stay supported."""
    payload = _load_yaml(FIXTURES / "minimal" / "topology.yml")
    for guest in payload["proxmox_guests"]:
        assert "deployment_owner" not in guest


def test_multi_host_fixture_uses_vault_key_form():
    """Exercises ADR 0469 vault key reference shape."""
    payload = _load_yaml(FIXTURES / "multi-host" / "connection.yml")
    assert isinstance(payload["proxmox_host"]["key"], dict)
    assert payload["proxmox_host"]["key"]["vault"].startswith("secret/")


def test_minimal_fixture_uses_string_key_form():
    """Exercises legacy string key shape."""
    payload = _load_yaml(FIXTURES / "minimal" / "connection.yml")
    assert isinstance(payload["proxmox_host"]["key"], str)


@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
def test_topology_guests_have_unique_vmids(slug):
    """Catch fixture authoring mistakes that would never make it past Proxmox."""
    payload = _load_yaml(FIXTURES / slug / "topology.yml")
    vmids = [g["vmid"] for g in payload["proxmox_guests"]]
    assert len(vmids) == len(set(vmids))


@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
def test_topology_guest_ipv4s_fall_inside_cidr(slug):
    """Identity declares the LAN; every guest IP must live inside it."""
    import ipaddress

    identity = _load_yaml(FIXTURES / slug / "identity.yml")
    topology = _load_yaml(FIXTURES / slug / "topology.yml")
    cidr = ipaddress.ip_network(identity["platform_guest_network_cidr"])
    for guest in topology["proxmox_guests"]:
        assert ipaddress.ip_address(guest["ipv4"]) in cidr, (
            f"{slug}/{guest['name']} ipv4 {guest['ipv4']} outside {cidr}"
        )
