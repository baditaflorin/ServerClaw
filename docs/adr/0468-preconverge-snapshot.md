# ADR 0468: Pre-Converge State Snapshot

- Status: Accepted
- Implementation Status: Implemented (`scripts/preconverge_snapshot.py compose` + `inspect`)
- Date: 2026-04-29
- Concern: incident-triage, half-applied-state-recovery
- Tags: snapshot, receipts, rollback, pre-converge
- Implements: improvement #7 from the 2026-04-29 reliability review (read-only half — automated rollback deferred)
- Depends on: ADR 0461, ADR 0466

---

## Context

When a converge breaks the host (oauth2-proxy collision, partial systemd restart, dangling docker container), the operator's first triage question is "what was running before this run started?". Today the answer requires SSH'ing into the box and running `systemctl`/`docker ps` from memory. There's no recorded baseline.

## Decision

`scripts/preconverge_snapshot.py compose` writes one `receipts/pre-converge-state/<host>-<run_id>.json` per converge with three sections:

- **systemd_units** — output of `systemctl list-unit-files --no-legend --plain` parsed to `{unit, load, active, sub}`.
- **docker_containers** — output of `docker ps -a --format json`.
- **managed_files** — sha256 + size + mtime for each path the role declares.

The Ansible role captures the three lists during a `pre_tasks` block and pipes them through this script.

`inspect` subcommand pretty-prints any snapshot for triage:

```bash
python3 scripts/preconverge_snapshot.py inspect --host nginx
```

### What this ADR explicitly defers

- **Automatic rollback.** Rollback is operator-judgement territory — different services have different idempotence guarantees. The snapshot is a read-only artifact that informs the operator's choice, not an automated revert.
- **Diff against ADR 0466 post-converge state.** Composes naturally; out of scope here.

## References

- [ADR 0461 — Atomic Receipt Write](0461-atomic-receipt-write-and-dangling-check.md)
- [ADR 0466 — Converge State Diff Receipts](0466-converge-state-diff-receipt.md)
