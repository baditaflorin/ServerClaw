# ADR 0048: Command Catalog And Approval Gates

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

