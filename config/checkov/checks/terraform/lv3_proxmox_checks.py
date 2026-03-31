from __future__ import annotations

from typing import Any

from checkov.common.models.enums import CheckCategories, CheckResult
from checkov.terraform.checks.module.base_module_check import BaseModuleCheck
from checkov.terraform.checks.provider.base_check import BaseProviderCheck
from checkov.terraform.checks.resource.base_resource_check import BaseResourceCheck


def _unwrap(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1:
            return _unwrap(value[0])
    return value


def _is_true(value: Any) -> bool:
    value = _unwrap(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _has_value(value: Any) -> bool:
    value = _unwrap(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _iter_block_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        blocks: list[dict[str, Any]] = []
        for item in value:
            blocks.extend(_iter_block_dicts(item))
        return blocks
    return []


def _module_source(value: Any) -> str:
    value = _unwrap(value)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _is_governed_proxmox_module(source: str) -> bool:
    return source.endswith("/proxmox-vm") or source.endswith("/proxmox-vm-destroyable")


class EnsureProxmoxVmDisksParticipateInBackup(BaseResourceCheck):
    def __init__(self) -> None:
        super().__init__(
            name="Ensure Proxmox VM disks participate in backup",
            id="CKV_LV3_1",
            categories=(CheckCategories.BACKUP_AND_RECOVERY,),
            supported_resources=("proxmox_virtual_environment_vm",),
            guideline="ADR 0306 requires repo-managed Proxmox VMs to keep disk backup enabled.",
        )

    def scan_resource_conf(self, conf: dict[str, list[Any]]) -> CheckResult:
        disks = _iter_block_dicts(conf.get("disk") or [])
        if not disks:
            self.evaluated_keys = ["disk"]
            return CheckResult.FAILED

        for index, disk in enumerate(disks):
            if not _is_true(disk.get("backup")):
                self.evaluated_keys = [f"disk/[{index}]/backup"]
                return CheckResult.FAILED

        self.evaluated_keys = ["disk"]
        return CheckResult.PASSED


class EnsureProxmoxVmMacAddressIsPinned(BaseResourceCheck):
    def __init__(self) -> None:
        super().__init__(
            name="Ensure Proxmox VM network devices pin a MAC address",
            id="CKV_LV3_2",
            categories=(CheckCategories.NETWORKING,),
            supported_resources=("proxmox_virtual_environment_vm",),
            guideline="ADR 0306 and the repo lessons learned require stable VM MAC identity.",
        )

    def scan_resource_conf(self, conf: dict[str, list[Any]]) -> CheckResult:
        devices = _iter_block_dicts(conf.get("network_device") or [])
        if not devices:
            self.evaluated_keys = ["network_device"]
            return CheckResult.FAILED

        for index, device in enumerate(devices):
            if not _has_value(device.get("mac_address")):
                self.evaluated_keys = [f"network_device/[{index}]/mac_address"]
                return CheckResult.FAILED

        self.evaluated_keys = ["network_device"]
        return CheckResult.PASSED


class EnsureProxmoxModuleCallsDeclareMacAddress(BaseModuleCheck):
    def __init__(self) -> None:
        super().__init__(
            name="Ensure Proxmox VM module calls declare mac_address",
            id="CKV_LV3_3",
            categories=(CheckCategories.NETWORKING,),
            guideline="ADR 0306 requires each governed Proxmox VM module call to pin a MAC address.",
        )

    def scan_module_conf(self, conf: dict[str, list[Any]]) -> CheckResult:
        source = _module_source(conf.get("source"))
        if not _is_governed_proxmox_module(source):
            self.evaluated_keys = []
            return CheckResult.UNKNOWN

        self.evaluated_keys = ["mac_address"]
        return CheckResult.PASSED if _has_value(conf.get("mac_address")) else CheckResult.FAILED


class EnsureProxmoxProviderTlsVerificationStaysEnabled(BaseProviderCheck):
    def __init__(self) -> None:
        super().__init__(
            name="Ensure Proxmox provider TLS verification stays enabled",
            id="CKV_LV3_4",
            categories=(CheckCategories.NETWORKING,),
            supported_provider=("proxmox",),
            guideline="ADR 0306 treats insecure=true as a governed warning until the live API path uses trusted TLS.",
        )

    def scan_provider_conf(self, conf: dict[str, list[Any]]) -> CheckResult:
        self.evaluated_keys = ["insecure"]
        return CheckResult.FAILED if _is_true(conf.get("insecure")) else CheckResult.PASSED


check = EnsureProxmoxVmDisksParticipateInBackup()
check2 = EnsureProxmoxVmMacAddressIsPinned()
check3 = EnsureProxmoxModuleCallsDeclareMacAddress()
check4 = EnsureProxmoxProviderTlsVerificationStaysEnabled()
