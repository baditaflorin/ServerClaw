# ADR 0459: Deployment Lifecycle CLI Parity (`use`/`new`/`bind`)

- Status: Accepted
- Implementation Status: Implemented (`use`/`new`/`bind` subcommands on `scripts/deployment.py`).
- Date: 2026-04-29
- Concern: operator-surface, agent-friendly-cli, multi-deployment-ergonomics
- Tags: multi-deployment, deployment-lifecycle, cli
- Implements: programmatic-CLI half of [ADR 0442](0442-multi-deployment-make-interface-and-worktree-binding.md)
- Depends on:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)
  - ADR 0442 (Multi-Deployment Make Interface)

---

## Context

[ADR 0442](0442-multi-deployment-make-interface-and-worktree-binding.md) sketches three operator commands for managing deployments:

- `make new-deployment slug=<slug> apex=<domain> operator='<name> <email>'`
- `make use-deployment slug=<slug>`
- `make bind-worktree slug=<slug>`

These targets ship in `mk/multi-deployment.mk` as Make-only entry points. They work fine for operators sitting at a terminal, but they have two limitations:

1. **No programmatic surface.** Agents, IDE plugins, hooks, and scripts that want to drive the deployment lifecycle have to shell out to `make`, parse output, and handle Make's own error semantics. There is no exit-code contract beyond Make's own pass/fail.
2. **No unit-testable boundary.** The shell loops inside Make targets are not addressable for pytest-style tests.

## Decision

Add three subcommands to `scripts/deployment.py` that mirror the Make targets:

- `python3 scripts/deployment.py use --slug <slug>` — writes `.local/active-deployment`.
- `python3 scripts/deployment.py new --slug <slug> --apex <domain> [--operator '<name> <email>']` — scaffolds `.local/deployments/<slug>/{identity,topology,profile,connection}.yml` plus the `generated/secrets/receipts/state` directories.
- `python3 scripts/deployment.py bind --slug <slug>` — writes a `.deployment` marker in the current worktree's git root.

Each subcommand:

- Validates the slug against `^[a-z0-9][a-z0-9_-]*$` (matches the directory naming rule already enforced by `_list_deployment_slugs`).
- Returns exit code `0` on success, `2` on usage / data error.
- Refuses to overwrite (`new`) or operate on a missing deployment (`use`, `bind`).
- Prints a human-readable next-steps block on success.

### Why CLI parity instead of Make-driven canonicalisation

The Make targets are not the source of truth — the data layout under `.local/deployments/<slug>/` is. Both the Make targets and the Python CLI produce the same files. Either path works; operators pick whichever is more natural for their context. The Python CLI is the **agent-friendly** surface; Make is the **terminal-friendly** surface.

The two surfaces are kept in sync by the contract:

- Files produced: `identity.yml`, `topology.yml`, `profile.yml`, `connection.yml` (ADR 0448), plus subdirectories `generated/secrets/receipts/state`.
- Active marker: `.local/active-deployment` (single line, slug only).
- Worktree marker: `.deployment` (single line, slug only) at the worktree's `.git` root.

If the Make targets ever change the file shape, this ADR's CLI must change with them — and vice versa. Both surfaces are exercised by tests in their respective workstreams.

## Consequences

- Agents (Claude Code sessions, MCP servers, IDE plugins) can drive deployment lifecycle via a typed CLI without shelling out to Make.
- The behaviour is now unit-tested — `tests/test_ws0462_deployment_lifecycle_cli.py` covers slug validation, file scaffolding, overwrite refusal, operator parsing, and worktree binding.
- A future workstream could promote the Make targets to thin wrappers around the Python CLI (eliminating duplicated scaffolding logic). Out of scope here — both surfaces work today.

## References

- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0442 — Multi-Deployment Make Interface & Worktree Binding](0442-multi-deployment-make-interface-and-worktree-binding.md)
- [ADR 0448 — Deployment Connection Registry](0448-deployment-connection-registry-and-wrapper.md)
- `mk/multi-deployment.mk` — the existing Make-target half of this contract.
