# WS-20261103: pve-0mcp memory budget runbook, status after stage 1

## Status

In review (branch `claude/pve-0mcp-budget-status`, ADR 0494). Documentation and tests only; nothing is applied by this change. The live changes it records were made on 2026-11-02 and verified.

## Goal

The runbook merged in PR 653 is a proposal that says "nothing applied", says the budget is 80.15 percent "today", and links from the alert that now computes 82.14 percent. A reader paged by that alert, or following the apply plan, would get a wrong picture: A3 is done, the swap file step has a stopgap in the way, and three VMs have fixed sizes the tables do not show.

## Change

- `docs/runbooks/pve-0mcp-memory-budget.md`: the title and an update line say stage 1 was partly applied; the sentences that were true only on 2026-11-01 are dated; a new section 11 lists each step (A1 not applied, A2 not done, A3 applied, VMs 171, 122 and 192 at fixed sizes, the alert shipped), the new totals (105,728 MiB guaranteed, 82.14 percent; maximums 124,928 MiB, 97.1 percent), the gap to the 80 percent alarm (2,755 MiB) and what the host did between the changes. Sections 1 to 10 are the 2026-11-01 snapshot and are not rewritten.
- `tests/test_proxmox_host_memory_budget.py`: `test_the_runbook_says_nothing_was_applied` is replaced by `test_the_runbook_says_which_steps_were_applied` and `test_the_status_section_adds_up_against_the_budget_table`; the second starts from the budget table and recomputes the totals and percentages, the before columns and the gap, and pins the sentences that carry them. Mutation-tested: wrong percentages, a wrong table cell, a removed status and a wrong gap are each caught.

## Open decisions it records, not takes

- A1: keep the 32 GiB stopgap swap file (on the busy NVMe, not in fstab) and make it persistent, or put the swap on the quiet NVMe as proposed and remove the stopgap.
- A2, and what else gets the footprint under 80 percent (2,755 MiB above it).
- VM 170 and the two Postgres VMs, which still hold memory above their floors.

## Verification

`tests/test_proxmox_host_memory_budget.py` and `tests/test_adopted_prometheus_rules.py` (50 passed), the workstream registry and branch validators, the diagram check, then the repository pre-push gate. No host is contacted.

## Rollback

Revert the commit. Nothing live depends on it.
