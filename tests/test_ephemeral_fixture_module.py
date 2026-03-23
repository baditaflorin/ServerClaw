from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_proxmox_vm_module_exposes_configurable_prevent_destroy() -> None:
    variables = (REPO_ROOT / "tofu" / "modules" / "proxmox-vm" / "variables.tf").read_text()
    main_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-vm" / "main.tf").read_text()

    assert 'variable "prevent_destroy"' in variables
    assert "prevent_destroy = var.prevent_destroy" in main_tf


def test_fixture_module_wraps_proxmox_vm_module() -> None:
    main_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-fixture" / "main.tf").read_text()
    outputs_tf = (REPO_ROOT / "tofu" / "modules" / "proxmox-fixture" / "outputs.tf").read_text()

    assert 'source = "../proxmox-vm"' in main_tf
    assert "prevent_destroy         = false" in main_tf
    assert 'output "ip_address"' in outputs_tf
