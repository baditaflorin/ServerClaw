# ADR 0227: Bounded Command Execution Via Systemd-Run And Approved Wrappers

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The platform already has a governed command catalog, but much of the actual
execution model still assumes a human or agent is sitting in an SSH shell.

That creates avoidable gaps:

- weak isolation between commands
- inconsistent timeout and resource boundaries
- variable logging and receipt capture
- more ambient power than routine commands should need

## Decision

We will execute routine governed commands through **repo-managed wrappers that
launch transient units with `systemd-run`**.

### Execution contract

Each governed command must declare:

- effective user
- working directory
- timeout and kill mode
- required environment contract
- resource limits or cgroup boundaries when relevant
- receipt and log destinations

The wrapper converts that contract into a transient systemd unit instead of
running the command inline inside the caller's shell.

### Security and audit rules

- routine commands run as `ops` or a dedicated service identity, not as `root`
- root-capable commands require an explicit, audited break-glass or elevated
  wrapper path
- stdout, stderr, exit code, and runtime metadata must be capturable after the
  initiating client disconnects

## Consequences

**Positive**

- Routine server-side commands become more reproducible and better bounded.
- Shell disconnects no longer imply task loss.
- The same governed command can be triggered from CLI, API, or workflow surfaces
  without changing its runtime isolation model.

**Negative / Trade-offs**

- Wrappers add implementation work compared with direct shell execution.
- Operators may need new debugging habits centered on unit metadata and logs.

## Boundaries

- This ADR does not replace full interactive shells for incident response or
  forensic work.
- `systemd-run` is a command execution envelope, not the higher-level workflow
  engine.

## Related ADRs

- ADR 0048: Command catalog and approval gates
- ADR 0066: Structured mutation audit log
- ADR 0170: Platform-wide timeout hierarchy
- ADR 0224: Server-resident operations as the default control model
- ADR 0226: Systemd units, timers, and paths for host-resident control loops
