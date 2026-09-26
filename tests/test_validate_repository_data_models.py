from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load_module("validate_repository_data_models", "scripts/validate_repository_data_models.py")


def test_proxmox_guest_aliases_do_not_require_real_vm_macaddr() -> None:
    vmid, name, ipv4, template_key, is_alias = models.validate_proxmox_guest(
        {
            "vmid": 920,
            "name": "docker-runtime",
            "role": "runtime-apps",
            "template_key": "lv3-debian-base",
            "ipv4": "10.10.10.12",
            "cidr": 24,
            "gateway4": "10.10.10.1",
            "macaddr": "BC:24:11:19:0A:920",
            "cores": 1,
            "memory_mb": 512,
            "disk_gb": 1,
            "tags": ["alias", "consolidation"],
            "packages": [],
        },
        "host_vars.proxmox_guests[0]",
    )

    assert (vmid, name, ipv4, template_key, is_alias) == (
        920,
        "docker-runtime",
        "10.10.10.12",
        "lv3-debian-base",
        True,
    )


def test_platform_vars_validation_reuses_tracked_identity_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    platform_vars_path = tmp_path / "platform.yml"
    platform_vars_path.write_text("sentinel: true\n", encoding="utf-8")
    calls: dict[str, object] = {}

    def fake_load_sources(
        skip_local_override: bool = False,
        *,
        skip_topology_override: bool = False,
        skip_generated_topology: bool = False,
    ):
        calls.update(
            skip_local_override=skip_local_override,
            skip_topology_override=skip_topology_override,
            skip_generated_topology=skip_generated_topology,
        )
        return {}, {}

    def fake_apply(host_vars: dict, overlay: dict) -> None:
        host_vars.update(overlay)

    monkeypatch.setattr(models, "PLATFORM_VARS_PATH", platform_vars_path)
    monkeypatch.setattr(models, "load_sources", fake_load_sources)
    monkeypatch.setattr(models, "missing_deployment_derived_platform_inputs", lambda: ())
    monkeypatch.setattr(
        models, "_load_generation_identity_overlay", lambda path: {"platform_domain": "tracked.example"}
    )
    monkeypatch.setattr(models, "_apply_generation_identity_overlay", fake_apply)
    monkeypatch.setattr(models, "build_platform_vars", lambda *, stack, host_vars: {"sentinel": True})

    models.validate_platform_vars()

    assert calls == {
        "skip_local_override": True,
        "skip_topology_override": True,
        "skip_generated_topology": True,
    }


def test_platform_vars_validation_uses_exported_identity_and_topology_selectors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    platform_vars_path = tmp_path / "platform.yml"
    identity_file = tmp_path / "identity.yml"
    topology_file = tmp_path / "topology.yml"
    platform_vars_path.write_text("sentinel: true\n", encoding="utf-8")
    identity_file.write_text("platform_domain: selected.example.net\n", encoding="utf-8")
    topology_file.write_text("proxmox_internal_ipv4: 10.77.0.1\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_IDENTITY_OVERLAY", str(identity_file))
    monkeypatch.setenv("PLATFORM_TOPOLOGY_OVERLAY", str(topology_file))
    calls: dict[str, object] = {}

    monkeypatch.setattr(models, "PLATFORM_VARS_PATH", platform_vars_path)
    monkeypatch.setattr(models, "missing_deployment_derived_platform_inputs", lambda: ())
    monkeypatch.setattr(
        models,
        "_apply_identity_override",
        lambda path: calls.update(identity_path=path),
    )
    monkeypatch.setattr(
        models,
        "_apply_topology_override",
        lambda path: calls.update(topology_path=path),
    )

    def fake_load_sources(
        skip_local_override: bool = False,
        *,
        skip_topology_override: bool = False,
        skip_generated_topology: bool = False,
    ):
        calls.update(
            skip_local_override=skip_local_override,
            skip_topology_override=skip_topology_override,
            skip_generated_topology=skip_generated_topology,
        )
        return {}, {}

    monkeypatch.setattr(models, "load_sources", fake_load_sources)
    monkeypatch.setattr(models, "build_platform_vars", lambda *, stack, host_vars: {"sentinel": True})

    models.validate_platform_vars()

    assert calls == {
        "identity_path": identity_file.resolve(),
        "topology_path": topology_file.resolve(),
        "skip_local_override": False,
        "skip_topology_override": False,
        "skip_generated_topology": True,
    }


def test_platform_vars_validation_skips_only_equivalence_without_deployment_inputs(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    platform_vars_path = tmp_path / "platform.yml"
    platform_vars_path.write_text("sentinel: true\n", encoding="utf-8")
    missing_path = tmp_path / "config" / "generated" / "dns-declarations.yaml"

    monkeypatch.setattr(models, "PLATFORM_VARS_PATH", platform_vars_path)
    monkeypatch.setattr(models, "missing_deployment_derived_platform_inputs", lambda: (missing_path,))
    monkeypatch.setattr(
        models,
        "load_sources",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("equivalence generation must not run")),
    )

    models.validate_platform_vars()

    assert "Skipping derived platform-vars equivalence check" in capsys.readouterr().out


def test_platform_vars_validation_remains_strict_with_deployment_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    platform_vars_path = tmp_path / "platform.yml"
    platform_vars_path.write_text("actual: true\n", encoding="utf-8")

    monkeypatch.setattr(models, "PLATFORM_VARS_PATH", platform_vars_path)
    monkeypatch.setattr(models, "missing_deployment_derived_platform_inputs", lambda: ())
    monkeypatch.setattr(models, "load_sources", lambda **_kwargs: ({}, {}))
    monkeypatch.setattr(models, "_load_generation_identity_overlay", lambda _path: {})
    monkeypatch.setattr(models, "_apply_generation_identity_overlay", lambda _host_vars, _overlay: None)
    monkeypatch.setattr(models, "build_platform_vars", lambda *, stack, host_vars: {"expected": True})

    with pytest.raises(ValueError, match="must match"):
        models.validate_platform_vars()
