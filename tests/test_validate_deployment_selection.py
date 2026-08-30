from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    module_path = REPO_ROOT / "scripts" / "validate_deployment_selection.py"
    spec = importlib.util.spec_from_file_location("validate_deployment_selection", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = _load_module()


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _selection_fixture(tmp_path: Path) -> dict[str, Path]:
    guests = {
        "nginx": "10.10.10.10",
        "docker-runtime": "10.10.10.20",
        "postgres": "10.10.10.50",
        "runtime-control": "10.10.10.92",
    }
    identity = _write_yaml(
        tmp_path / "identity.yml",
        {
            "platform_domain": "selected.example",
            "management_ipv4": "192.0.2.10",
            "management_gateway4": "192.0.2.1",
            "management_interface": "eno1",
            "host_public_hostname": "selected-host",
        },
    )
    topology = _write_yaml(
        tmp_path / "topology.yml",
        {
            "proxmox_internal_ipv4": "10.10.10.1",
            "proxmox_guests": [{"name": name, "ipv4": address} for name, address in guests.items()],
            "platform_service_topology": {
                "authentik": {"owning_vm": "runtime-control"},
                "glitchtip": {"owning_vm": "docker-runtime"},
                "openbao": {"owning_vm": "runtime-control"},
            },
        },
    )
    tracked_platform = _write_yaml(
        tmp_path / "platform.yml",
        {
            "platform_generation": {
                "host_vars_source": "topology.yml",
                "identity_overlay": {
                    "platform_domain": "selected.example",
                    "management_ipv4": "192.0.2.10",
                    "management_gateway4": "192.0.2.1",
                    "management_interface": "eno1",
                    "host_public_hostname": "selected-host",
                },
            },
            "platform_host": {
                "management": {"ipv4": "192.0.2.10"},
                "network": {"internal_ipv4": "10.10.10.1"},
            },
            "platform_guest_catalog": {
                "by_name": {name: {"name": name, "ipv4": address} for name, address in guests.items()}
            },
            "platform_service_topology": {
                "authentik": {
                    "owning_vm": "runtime-control",
                    "private_ip": "10.10.10.92",
                    "public_hostname": "id.selected.example",
                },
                "glitchtip": {
                    "owning_vm": "docker-runtime",
                    "private_ip": "10.10.10.20",
                    "public_hostname": "errors.selected.example",
                },
                "openbao": {
                    "owning_vm": "runtime-control",
                    "private_ip": "10.10.10.92",
                },
            },
        },
    )
    service_registry = _write_yaml(
        tmp_path / "platform_services.yml",
        {
            "platform_service_registry": {
                "authentik": {"host_group": "runtime-control"},
                "glitchtip": {"host_group": "docker-runtime"},
                "openbao": {"host_group": "runtime-control"},
            }
        },
    )
    inventory = _write_yaml(
        tmp_path / "inventory.yml",
        {
            "all": {
                "children": {
                    "production": {"hosts": dict.fromkeys(guests)},
                    "lv3_guests": {"hosts": {name: {"ansible_host": address} for name, address in guests.items()}},
                }
            }
        },
    )
    return {
        "identity": identity,
        "topology": topology,
        "tracked_platform": tracked_platform,
        "service_registry": service_registry,
        "inventory": inventory,
    }


def _validate(paths: dict[str, Path], **overrides):
    kwargs = {
        "identity_path": paths["identity"],
        "topology_path": paths["topology"],
        "inventory_paths": [paths["inventory"]],
        "services": ["authentik", "glitchtip", "openbao"],
        "required_hosts": ["nginx", "postgres"],
        "environment": "production",
        "tracked_platform_path": paths["tracked_platform"],
        "service_registry_path": paths["service_registry"],
    }
    kwargs.update(overrides)
    return validator.validate_deployment_selection(**kwargs)


def test_valid_selection_resolves_only_tracked_hosts(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)

    result = _validate(paths)

    assert result["platform_domain"] == "selected.example"
    assert result["services"] == {
        "authentik": "runtime-control",
        "glitchtip": "docker-runtime",
        "openbao": "runtime-control",
    }
    assert result["required_hosts"] == ["docker-runtime", "nginx", "postgres", "runtime-control"]


def test_rejects_identity_from_a_different_deployment(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    _write_yaml(
        paths["identity"],
        {
            "platform_domain": "unrelated.example",
            "management_ipv4": "198.51.100.20",
            "management_gateway4": "198.51.100.1",
            "management_interface": "eno1",
            "host_public_hostname": "unrelated-host",
        },
    )

    with pytest.raises(validator.DeploymentSelectionError, match="does not exactly match"):
        _validate(paths)


def test_rejects_topology_from_a_different_deployment(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    topology = yaml.safe_load(paths["topology"].read_text(encoding="utf-8"))
    next(guest for guest in topology["proxmox_guests"] if guest["name"] == "runtime-control")["ipv4"] = "10.10.10.92"
    _write_yaml(paths["topology"], topology)

    with pytest.raises(validator.DeploymentSelectionError, match="guest addresses do not match"):
        _validate(paths)


def test_rejects_explicit_inventory_that_overrides_hosts_with_another_deployment(
    tmp_path: Path,
) -> None:
    paths = _selection_fixture(tmp_path)
    unrelated_inventory = _write_yaml(
        tmp_path / "unrelated-inventory.yml",
        {
            "all": {
                "children": {
                    "production": {"hosts": {"runtime-control": None}},
                    "lv3_guests": {"hosts": {"runtime-control": {"ansible_host": "10.10.10.92"}}},
                }
            }
        },
    )

    with pytest.raises(validator.DeploymentSelectionError, match="inventory address for 'runtime-control'"):
        _validate(paths, inventory_paths=[paths["inventory"], unrelated_inventory])


def test_rejects_effective_inventory_override_from_all_hosts(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    unrelated_inventory = _write_yaml(
        tmp_path / "unrelated-all-hosts.yml",
        {"all": {"hosts": {"runtime-control": {"ansible_host": "10.10.10.92"}}}},
    )

    with pytest.raises(validator.DeploymentSelectionError, match="inventory address for 'runtime-control'"):
        _validate(paths, inventory_paths=[paths["inventory"], unrelated_inventory])


def test_rejects_incomplete_fingerprint_and_unsafe_identity_keys(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    tracked = yaml.safe_load(paths["tracked_platform"].read_text(encoding="utf-8"))
    tracked["platform_generation"]["identity_overlay"].pop("management_gateway4")
    _write_yaml(paths["tracked_platform"], tracked)

    with pytest.raises(validator.DeploymentSelectionError, match="missing canonical fields"):
        _validate(paths)

    paths = _selection_fixture(tmp_path / "unsafe")
    identity = yaml.safe_load(paths["identity"].read_text(encoding="utf-8"))
    identity["ansible_host"] = "10.10.10.92"
    _write_yaml(paths["identity"], identity)
    with pytest.raises(validator.DeploymentSelectionError, match="forbidden structural"):
        _validate(paths)


def test_rejects_nonproduction_environment_and_stale_config_prefix(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    with pytest.raises(validator.DeploymentSelectionError, match="environment=production"):
        _validate(paths, environment="clone")

    identity = yaml.safe_load(paths["identity"].read_text(encoding="utf-8"))
    identity["platform_config_prefix"] = "wrong"
    _write_yaml(paths["identity"], identity)
    with pytest.raises(validator.DeploymentSelectionError, match="canonical domain prefix"):
        _validate(paths)


def test_rejects_service_owner_drift_between_registry_and_topology(tmp_path: Path) -> None:
    paths = _selection_fixture(tmp_path)
    topology = yaml.safe_load(paths["topology"].read_text(encoding="utf-8"))
    topology["platform_service_topology"]["authentik"]["owning_vm"] = "docker-runtime"
    _write_yaml(paths["topology"], topology)

    with pytest.raises(validator.DeploymentSelectionError, match="service registry requires"):
        _validate(paths)


def _recipe_lines(makefile: str, target: str) -> list[str]:
    block = makefile.split(f"{target}:\n", 1)[1].split("\n\n", 1)[0]
    return [line.strip() for line in block.splitlines() if line.startswith("\t") and line.strip()]


def test_sensitive_mutation_targets_run_selection_guard_first() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert _recipe_lines(makefile, "converge-authentik")[0] == ("$(MAKE) preflight-authentik-deployment-selection")
    assert _recipe_lines(makefile, "converge-glitchtip")[0] == ("$(MAKE) preflight-glitchtip-deployment-selection")
    assert _recipe_lines(makefile, "converge-outline")[0] == ("$(MAKE) preflight-outline-deployment-selection")
    assert _recipe_lines(makefile, "converge-openbao")[0] == ("$(MAKE) preflight-openbao-deployment-selection")
    assert _recipe_lines(makefile, "bootstrap-openbao-runtime-secret-provisioner")[0] == (
        "$(MAKE) preflight-openbao-deployment-selection"
    )


def test_identity_selector_does_not_implicitly_append_shared_local_inventory(tmp_path: Path) -> None:
    identity = _write_yaml(tmp_path / "identity.yml", {"management_ipv4": "192.0.2.10"})
    topology = _write_yaml(tmp_path / "topology.yml", {})

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-n",
            "syntax-check-authentik",
            f"PLATFORM_IDENTITY_OVERLAY={identity}",
            f"PLATFORM_TOPOLOGY_OVERLAY={topology}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"-i {REPO_ROOT / 'inventory' / 'hosts.yml'}" in result.stdout
    assert ".local/inventory/hosts.yml" not in result.stdout


def test_preflight_targets_check_both_explicit_selectors_before_validator() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "preflight-authentik-deployment-selection",
        "preflight-glitchtip-deployment-selection",
        "preflight-outline-deployment-selection",
        "preflight-openbao-deployment-selection",
    ):
        recipes = _recipe_lines(makefile, target)
        assert "PLATFORM_IDENTITY_OVERLAY" in recipes[0]
        assert "PLATFORM_TOPOLOGY_OVERLAY" in recipes[1]
        assert '"$(env)" = "production"' in recipes[2]
        assert "validate_deployment_selection.py" in recipes[3]
        assert '--environment "$(env)"' in recipes[3]


@pytest.mark.parametrize(
    "target",
    [
        "preflight-authentik-deployment-selection",
        "preflight-glitchtip-deployment-selection",
        "preflight-outline-deployment-selection",
        "preflight-openbao-deployment-selection",
    ],
)
def test_missing_selectors_fail_before_any_deployment_validation_command(target: str) -> None:
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            target,
            "PLATFORM_IDENTITY_OVERLAY=",
            "PLATFORM_TOPOLOGY_OVERLAY=",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "set PLATFORM_IDENTITY_OVERLAY" in output
    assert "validate_deployment_selection.py" not in output
    assert "generate_platform_vars.py" not in output


def test_identity_overlay_clone_default_is_rejected_before_validator(tmp_path: Path) -> None:
    identity = _write_yaml(tmp_path / "identity.yml", {"platform_domain": "selected.example"})
    topology = _write_yaml(tmp_path / "topology.yml", {})

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "preflight-authentik-deployment-selection",
            f"PLATFORM_IDENTITY_OVERLAY={identity}",
            f"PLATFORM_TOPOLOGY_OVERLAY={topology}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "set env=production" in output
    assert "validate_deployment_selection.py" not in output
