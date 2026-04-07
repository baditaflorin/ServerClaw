# ADR 0030: Role Interface Contracts And Defaults Boundaries

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.31.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository now has multiple playbooks and roles that share state through large inventory-wide variable files, especially `inventory/group_vars/all.yml`.

That has worked for rapid delivery, but it creates codebase risks:

- role inputs are not obvious from the role directory itself
- adding a new role tends to grow global variable scope instead of keeping configuration local
- required inputs are discovered late, often during convergence instead of during code review
- refactoring one area can silently break another because the variable contract is implicit

As the number of guests and service-specific roles grows, hidden role coupling becomes a bigger maintenance problem than the role logic itself.

## Decision

We will make each role own an explicit interface contract.

The contract will require:

1. Each reusable role to declare stable defaults in `roles/<role>/defaults/main.yml`.
2. Each role to validate required inputs near the top of execution with explicit assertions.
3. Shared inventory files to hold only cross-role facts and platform-wide values.
4. Role-specific knobs to move out of `inventory/group_vars/all.yml` when they are not genuinely platform-global.
5. New roles to document their expected inputs and outputs in a short `README.md` or equivalent role-level note.

## Consequences

- Role reuse becomes easier because required inputs are visible where the role lives.
- Code review gets faster because variable movement is no longer hidden in large shared files.
- Refactors become safer because missing inputs fail early and explicitly.
- Initial migration will touch many existing roles and should be done incrementally, not in one opaque sweep.

## Implementation Notes

- Reusable roles now declare local interfaces through `defaults/main.yml`, a short role `README.md`, and early `assert` validation near the top of `tasks/main.yml`.
- Role-owned settings for Docker runtime, PostgreSQL, monitoring, build telemetry, edge publication, and related guest services were moved out of shared inventory files when they were not genuinely platform-global.
- Callers such as the Docker runtime, guest access, PostgreSQL, and backup playbooks now rely on role defaults instead of importing extra role-local variable files.
- Shared inventory remains for cross-role platform facts such as topology, base host policy, guest connection behavior, and truly common Proxmox settings.
