# WS-0537: Activate the agent-history guest

## Status

In progress. The pull request is open against `main` (it was prepared on top of ws-0534 and rebased after #598 merged on 2026-10-29), and not merged. Nothing is applied or provisioned; no `[live-apply]` marker.

## Goal

ADR 0494 declared VM 155 (`agent-history`) with `lifecycle: planned`, which made the declaration inert: the default guest set of `proxmox-install.yml`, the guests role, every scoped run and the per-guest playbook all refuse or skip a planned guest. This change is the owner's activation: one reviewed change, and the recorded approval of the capacity decision.

## Change

- `inventory/host_vars/proxmox-host.yml`: the `lifecycle: planned` line of VM 155 is deleted (the comment now says it was activated on 2026-10-29 and what that means).
- `inventory/hosts.yml`, regenerated with `make generate-inventory`: the `planned_guests` group is still emitted and is now empty (so the scoped patterns that end in `:!planned_guests` never name an unknown group); `agent-history` stays in `lv3_guests`.
- `tests/test_planned_guests.py`, `tests/test_generate_inventory.py`: nothing real is planned now, so the guard is pinned with synthetic planned guests (the default set skips them, the role and the per-guest playbook refuse them) and the real inventory is asserted to have an empty `planned_guests`.
- `docs/adr/0494-agent-history.md` (an Activation line, the decision 7 and consequences wording, an activation record with the capacity record and the written exception) and `docs/runbooks/configure-agent-history.md` (activated, with the hazard below); the header comment of `playbooks/agent-history-vm.yml`.

## Capacity record

`pve-0mcp` `MemAvailable` was 15.5 GiB (12.3 %) at 09:30Z on 2026-10-29 after VM 130 (`docker-build-lv3`) was trimmed from 20 to 10 GiB (floor); VM 155 needs a 6 GiB floor, so after provisioning the host stays above the 5 % critical line (6.3 GiB) and below the owner's 15 % placement guard. The written exception to that guard: owner decision 2026-10-29, option B plus the VM 130 trim; the store is rebuildable from the laptops. Not measured by the author of this change: the figures are relayed, and the 24-hour minimum was not measured.

## What merging does and does not do

Does: remove the guards that kept the declaration inert. Does not: create the VM, run any playbook, or change any host.

**Merge it immediately before provisioning.** From the merge, until the guest exists: an unrestricted `make provision-guests` would clone VM 155 and rewrite the hardware of every other declared guest, and the scoped runs on `lv3_guests` (`converge-guest-network-policy` and the other scoped converges) reach 10.10.10.55, which does not exist, and fail on it. Provision only with `make provision-agent-history-vm`. If provisioning is postponed, declare the guest `lifecycle: planned` again.

The service bundle's `lifecycle_status` and the capacity model's `status` stay `planned`: they describe the guest's existence, which a later change records after provisioning.
