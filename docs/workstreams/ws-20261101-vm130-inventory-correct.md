# WS-20261101: VM 130 (the 0mcp CI builder) declared as the live VM runs

## Status

In review (branch `claude/vm130-inventory-correct`, ADR 0494 for the earlier trim). Inventory and documentation only. Nothing is applied: the live VM already matches what the inventory now says.

## Goal

On 2026-11-01 the 0mcp hypervisor ran out of memory and VM 130 (`docker-build-lv3`, the CI builder) was restarted at 14336 MiB with ballooning off. The inventory entry for vmid 130 still described an older, smaller VM. The `proxmox_guests` role runs `qm set <vmid> --cores <cores> --memory <memory_mb> --balloon 0` on every declared guest, so a `provision-guests` run would have shrunk the production CI builder to the declared numbers. The goal is that git says what the VM is.

## Change

- `inventory/host_vars/proxmox-host.yml`, vmid 130: `cores` 12 -> 20, `memory_mb` 10240 -> 14336, `disk_gb` 320 -> 600, and the comment says why (the hypervisor memory exhaustion, balloon off, `disk_gb` used only on clone).
- `config/0mcp/docker-build-lv3/README.md`: the intro line says 14 GiB fixed, a dated section "Memory 2026-11-01" records the restart, the live `qm config 130` values and the rollback, the 2026-10-29 section points to it, and the rebuild recipe says 20 cores, 14336 MiB fixed, 600 GB (it said 16 GB and 420 GB).

## Verified live (read-only)

`qm config 130` on the 0mcp hypervisor, 2026-11-01: `cores: 20`, `memory: 14336`, `balloon: 0`, `hotplug: disk,network,usb,cpu,memory`, `numa: 1`, `onboot: 1`, `scsi0: local-nvme:130/vm-130-disk-0.qcow2,discard=on,size=600G`, status running. Nothing was set.

## Not in this change

- `inventory/group_vars/platform.yml` is generated and was already stale for several guests (it still says 24576 MB for VM 130, and has no VM 155). A dry run of `scripts/generate_platform_vars.py` after this edit differs from the committed file in 1043 lines, so regenerating it here would ship other guests' declared changes. Nothing reads guest sizes from it (`platform_guest_catalog` is read for addresses only). It is refreshed by the next full regeneration.
- `publication/templates/proxmox-host.yml` is the sanitised public template, not this deployment's inventory.
- The builder-slot numbers of the 2026-10-29 section are not re-measured here.

## Verification

Offline: `tests/test_docker_build_lv3_config.py` and the inventory and workstream validators, then the repository pre-push gate. No host is contacted by the tests.

## Rollback

Revert the commit. The live VM is unaffected either way.
