# ADR 0048: Command Catalog And Approval Gates

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

Agentic systems become dangerous when a "remote command" is just arbitrary shell text with unclear inputs, no prechecks, and no evidence trail.

This repository already values runbooks, automation, and live-apply receipts. The next step is to make remote mutation contracts explicit.

## Decision

All recurring mutating operations must be represented as named command contracts.

Each contract must define:

- an operation name
- inputs and expected preconditions
- preferred execution path such as Ansible, Proxmox API, Windmill flow, or controlled SSH
- verification checks
- evidence or receipt expectations
- stop or rollback guidance when verification fails

Steady-state rules:

1. prefer API and automation entry points over free-form shell
2. use raw SSH one-liners only for break-glass or diagnosis
3. if a manual mutation is unavoidable, document it in the same turn
4. require a dry-run, diff, or preflight step whenever the execution path supports it

## Consequences

- Another assistant can understand what "safe remote execution" means without hidden chat context.
- Sensitive commands become reviewable artifacts instead of folklore.
- Approval can be attached to operation names and scopes instead of trying to judge raw shell text every time.

## Implementation Notes

- The canonical command-contract catalog now lives in [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/command-catalog.json).
- [scripts/command_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/command_catalog.py) validates the catalog, renders one contract, and evaluates approval gates against workflow lifecycle, requester class, approvals, preflight, validation, and receipt-planning inputs.
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/Makefile) now exposes `make commands` and `make command-info COMMAND=<id>` so operators and assistants can inspect mutating command contracts without reconstructing them from prose.
- Repository data-model validation now cross-checks the command catalog alongside the workflow catalog, receipts, control-plane lanes, and canonical stack state.
- Operator usage is documented in [docs/runbooks/command-catalog-and-approval-gates.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/command-catalog-and-approval-gates.md).
- Live verification from `main` on 2026-03-22 validated the command catalog and exercised the approval gate for `configure-network` as the representative recurring host mutation contract.
