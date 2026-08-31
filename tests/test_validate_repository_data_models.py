from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
