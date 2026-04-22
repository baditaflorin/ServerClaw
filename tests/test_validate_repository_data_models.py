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
            "ipv4": "10.20.10.12",
            "cidr": 24,
            "gateway4": "10.20.10.1",
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
        "10.20.10.12",
        "lv3-debian-base",
        True,
    )
