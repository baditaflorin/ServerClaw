from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_proxmox_vm_module_keeps_literal_destroy_protection() -> None:
    main_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-vm" / "main.tf").read_text()

    assert "prevent_destroy = true" in main_tf


def test_fixture_module_wraps_proxmox_vm_module() -> None:
    main_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-fixture" / "main.tf").read_text()
    outputs_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-fixture" / "outputs.tf").read_text()
    destroyable_main_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-vm-destroyable" / "main.tf").read_text()

    assert 'source = "../proxmox-vm-destroyable"' in main_tf
    assert "prevent_destroy = false" in destroyable_main_tf
    assert 'output "ip_address"' in outputs_tf
