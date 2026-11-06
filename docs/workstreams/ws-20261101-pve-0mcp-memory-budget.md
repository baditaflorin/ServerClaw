# WS-20261101: pve-0mcp memory budget (proposal, git only)

## Status

Merged (PR 653, `1cee7e96`, ADR 0494 for the memory placement rule) and the alert applied live on 2026-11-03 at 17:42Z; receipt `2026-11-03-pve-0mcp-memory-budget-alert-monitoring-live-apply`. The runbook and the alert were written read-only (no host was changed by the proposal itself); the apply plan's steps are separate decisions, recorded in the runbook as they are taken.

## Goal

On 2026-11-01 `pve-0mcp` (128,716 MiB, 19 running VMs) fell to 3.9 percent available memory with its 4 GiB of swap full and recovered only after VM 130 was restarted at a fixed 14,336 MiB. The question this workstream answers is what the host should promise its guests: which memory numbers are guaranteed (balloon floors and fixed VMs), what the guests really use, which floors can move, whether the host needs more swap or KSM, and how a change reaches the host. The owner decides what is applied.

## Change

- `docs/runbooks/pve-0mcp-memory-budget.md`: where VM memory is defined, the seven-day measured table, the budget rule and table (target 75 percent of RAM for floors plus fixed VMs, alarm above 80), floor proposals, fixed-VM and KSM and swap verdicts, a staged apply plan with undo, risks and the one decision.
- `config/prometheus/rules/proxmox-host-memory-budget.yml` (alert `ProxmoxHostGuaranteedMemoryOverBudget`, scoped to `pve_host="0mcp"`), `tests/promtool/proxmox_host_memory_budget_rules_test.yml`, `tests/test_proxmox_host_memory_budget.py` (pins the rule, runs promtool, checks the runbook's arithmetic), and the file added to the monitoring role's adopted list (`defaults/main.yml`, `tests/test_adopted_prometheus_rules.py`).

## Not in this change

- No `qm set`, no VM restart, no swap or KSM change, no sysfs write, no package install. Shipping the rule file to the monitoring VM (role copy plus a Prometheus reload) is a separate approved step; merging does not do it.
- `inventory/host_vars/proxmox-host.yml` is not edited: it disagrees with the live VMs for six guests (listed in the runbook); reconciling it is a separate change.
- `config/capacity-model.json` is not edited (its guest list is stale; the runbook says where).

## Verification

Promtool check and unit tests, the pytest pin, ruff, the workstream validators, then the repository pre-push gate. The alert expression was also evaluated read-only on the live 0mcp Prometheus (0.8015 for `0mcp`, the same number as the hand sum of `qm config`).

## Rollback

Revert the commit, and remove the live rule file: `ssh 0mcp_monitoring 'sudo rm /etc/prometheus/rules/proxmox-host-memory-budget.yml && sudo systemctl kill --kill-whom=main --signal=HUP 0mcp-prometheus.service'` (the file did not exist on the VM before, so there is no backup copy). The alert is a warning that only notifies.

## Live apply

- Applied on 2026-11-03 at 17:42Z to the monitoring VM (`monitoring-lv3`) with a targeted Ansible play that installs `config/prometheus/rules/proxmox-host-memory-budget.yml` (sha256 `6e51657b...5aba7`, main `1cee7e96`) with the `monitoring_vm` role's own parameters (root:prometheus, 0640, promtool-validated) and reloads Prometheus with SIGHUP. Check mode first: one change, the new file.
- Result: the alert is loaded in group `proxmox_host_memory_budget`, healthy, state pending; it computes 0.8214 (guaranteed 105,728 MiB of 128,717 MiB after the 2026-11-02 changes of VMs 120, 122, 171 and 192) against the 0.80 threshold, so it fires as a warning after its one hour. Only that file was added to `/etc/prometheus/rules`; the reload also loaded `fleet-log-shipping.yml` (PR 649), which had been on the VM but not loaded (2 rules, healthy, quiet).
- Rollback: see below. Receipt: `2026-11-03-pve-0mcp-memory-budget-alert-monitoring-live-apply`. `platform_version` 0.179.54 to 0.179.55.
