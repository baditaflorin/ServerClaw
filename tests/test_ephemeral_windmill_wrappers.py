from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script_relative_path", "expected_result"),
    [
        ("config/windmill/scripts/ephemeral-pool-reconciler.py", {"status": "pool-ok"}),
        ("config/windmill/scripts/ephemeral-vm-reaper.py", {"status": "reaper-ok"}),
        ("config/windmill/scripts/fixture-expiry-reaper.py", {"status": "reaper-ok"}),
    ],
)
def test_ephemeral_windmill_wrappers_load_repo_fixture_manager_even_with_conflicting_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_relative_path: str,
    expected_result: dict[str, str],
) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir()
    (repo_root / "inventory" / "group_vars").mkdir(parents=True)
    (repo_root / "inventory" / "host_vars").mkdir(parents=True)
    (repo_root / "tests" / "fixtures").mkdir(parents=True)
    (repo_root / "receipts" / "fixtures").mkdir(parents=True)
    (repo_root / ".local" / "fixtures").mkdir(parents=True)
    (repo_root / ".local" / "proxmox-api").mkdir(parents=True)

    (repo_root / "config" / "controller-local-secrets.json").write_text('{"secrets": {}}\n', encoding="utf-8")
    (repo_root / "config" / "vm-template-manifest.json").write_text('{"templates": {}}\n', encoding="utf-8")
    (repo_root / "config" / "capacity-model.json").write_text(
        '{"schema_version": "1.0.0", "reservations": []}\n', encoding="utf-8"
    )
    (repo_root / "config" / "ephemeral-capacity-pools.json").write_text(
        '{"schema_version": "1.0.0", "defaults": {"max_local_active_leases": 3, "protected_capacity_class": "ephemeral-burst-local", "spillover_domain": "hetzner-cloud-burst", "warm_lifetime_minutes": 1440}, "pools": []}\n',
        encoding="utf-8",
    )
    (repo_root / "inventory" / "group_vars" / "all.yml").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text("", encoding="utf-8")
    (repo_root / ".local" / "proxmox-api" / "lv3-automation-primary.json").write_text(
        '{"api_url": "https://proxmox.example.invalid:8006/api2/json", "full_token_id": "token", "value": "secret"}\n',
        encoding="utf-8",
    )
    (repo_root / "scripts" / "fixture_manager.py").write_text(
        "\n".join(
            [
                "from dataclasses import dataclass",
                "import vmid_allocator",
                "@dataclass",
                "class ReceiptSummary:",
                "    status: str",
                "class DummyAllocator:",
                "    def __init__(self):",
                "        self.read_api_credentials = lambda **kwargs: ('https://proxmox.example.invalid:8006/api2/json', 'token')",
                "vmid_allocator = DummyAllocator()",
                "def reconcile_pools(pool_id=None):",
                "    return {'status': ReceiptSummary('pool-ok').status}",
                "def reap_expired():",
                "    return {'status': ReceiptSummary('reaper-ok').status}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "scripts" / "vmid_allocator.py").write_text("MARKER = 'repo-sibling-import'\n", encoding="utf-8")

    conflicting_module = types.ModuleType("fixture_manager")
    conflicting_module.vmid_allocator = types.SimpleNamespace(
        read_api_credentials=lambda **kwargs: ("conflict", "conflict")
    )
    monkeypatch.setitem(sys.modules, "fixture_manager", conflicting_module)

    wrapper = _load_module(
        f"test_{Path(script_relative_path).stem.replace('-', '_')}",
        REPO_ROOT / script_relative_path,
    )

    assert wrapper.main(repo_path=str(repo_root)) == expected_result


def test_ephemeral_pool_reconciler_uses_worker_local_bootstrap_key(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir()
    (repo_root / "inventory" / "group_vars").mkdir(parents=True)
    (repo_root / "inventory" / "host_vars").mkdir(parents=True)
    (repo_root / "tests" / "fixtures").mkdir(parents=True)
    (repo_root / "receipts" / "fixtures").mkdir(parents=True)
    (repo_root / ".local" / "proxmox-api").mkdir(parents=True)
    (repo_root / ".local" / "ssh").mkdir(parents=True)

    (repo_root / "config" / "controller-local-secrets.json").write_text('{"secrets": {}}\n', encoding="utf-8")
    (repo_root / "config" / "vm-template-manifest.json").write_text('{"templates": {}}\n', encoding="utf-8")
    (repo_root / "config" / "capacity-model.json").write_text(
        '{"schema_version": "1.0.0", "reservations": []}\n', encoding="utf-8"
    )
    (repo_root / "config" / "ephemeral-capacity-pools.json").write_text(
        '{"schema_version": "1.0.0", "defaults": {"max_local_active_leases": 3, "protected_capacity_class": "ephemeral-burst-local", "spillover_domain": "hetzner-cloud-burst", "warm_lifetime_minutes": 1440}, "pools": []}\n',
        encoding="utf-8",
    )
    (repo_root / "inventory" / "group_vars" / "all.yml").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text("", encoding="utf-8")
    (repo_root / ".local" / "proxmox-api" / "lv3-automation-primary.json").write_text(
        '{"api_url": "https://proxmox.example.invalid:8006/api2/json", "full_token_id": "token", "value": "secret"}\n',
        encoding="utf-8",
    )
    worker_key = repo_root / ".local" / "ssh" / "bootstrap.id_ed25519"
    worker_key.write_text("PRIVATE\n", encoding="utf-8")
    (repo_root / "scripts" / "vmid_allocator.py").write_text("MARKER = 'repo-sibling-import'\n", encoding="utf-8")
    (repo_root / "scripts" / "fixture_manager.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import vmid_allocator",
                "class DummyAllocator:",
                "    def __init__(self):",
                "        self.read_api_credentials = lambda **kwargs: ('https://proxmox.example.invalid:8006/api2/json', 'token')",
                "vmid_allocator = DummyAllocator()",
                "def bootstrap_private_key():",
                "    return Path('/controller-only/bootstrap-key')",
                "def reconcile_pools(pool_id=None):",
                "    return {'bootstrap_key': str(bootstrap_private_key())}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    wrapper = _load_module(
        "test_ephemeral_pool_reconciler_bootstrap",
        REPO_ROOT / "config/windmill/scripts/ephemeral-pool-reconciler.py",
    )

    assert wrapper.main(repo_path=str(repo_root)) == {"bootstrap_key": str(worker_key)}
