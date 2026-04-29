# ADR 0474: Phase 12 — Receipt Mass-Refresh + `make heal-receipts`

- Status: Proposed
- Implementation Status: In progress
- Date: 2026-04-29
- Concern: drift, automation, operator-burden
- Tags: receipts, heal, doctor, batch
- Reservation: res-0474-phase-12-receipt-mass-refresh
- Implements: Phase 12 of the postmortem self-healing roadmap
- Depends on:
  - ADR 0449 — `scripts/refresh_safe_receipts.py` classifier
  - ADR 0451 — `scripts/heal.py` orchestrator

## Context

Phase 4 (`refresh_safe_receipts.py`) classifies stale receipts into
`safe_to_refresh` / `needs_review` / `unknown` and supports `--apply`
to bump the safe set in `versions/stack.yaml` in a single commit.

In production, the `safe_to_refresh` count fluctuates between 60 and
80 services. Each operator session runs `--apply` once at most, and
the bump goes in next to the actual work. The work-of-the-week
churns through that backlog only incidentally.

What's missing: a single command that closes the loop end-to-end —
classify, apply, summarise, exit cleanly — that an operator (or a
scheduled cron, or `make heal --apply`) can invoke without thinking
about flags. And a doctor surface that flags when the safe-to-refresh
backlog grows past a threshold so the operator knows to run it.

## Decision

Two surfaces:

### Phase 12.1 — `scripts/mass_refresh_receipts.py`

Thin wrapper around `refresh_safe_receipts.py`:

1. Run the classifier (`--json`).
2. Print a one-line summary (`safe / needs_review / unknown / total`).
3. If `--apply` and `safe_to_refresh > 0`, invoke
   `refresh_safe_receipts.py --apply` to land the bump commit.
4. If `--apply` and the working tree is dirty, refuse (clean exit
   with a clear message — same contract as the underlying tool).
5. Optionally write a YAML receipt under
   `receipts/heal-receipts/<YYYY-MM-DDTHH:MM:SSZ>.yaml` recording the
   classification snapshot + commit sha (so the next operator can
   audit when the last mass refresh ran).

### Phase 12.2 — `make heal-receipts`

```make
heal-receipts:
    uv run --with pyyaml python scripts/mass_refresh_receipts.py --apply
```

And `make heal-receipts-dry-run` for the read-only path.

### Phase 12.3 — doctor surface

New probe in `scripts/doctor.py` (`probe_safe_refresh_backlog`) that
flags `[!]` when `safe_to_refresh > 25`. The threshold matches the
"a session's worth of bumps" ceiling — past that and the operator
should run `make heal-receipts` ahead of any other work.

## Consequences

- One-command receipt sweep: `make heal-receipts` or
  `make heal --apply` (which already iterates every doctor heal).
- Doctor backlog visibility — surfaces ahead of routine work.
- Receipt under `receipts/heal-receipts/` audits when each sweep ran.
- ~15 new tests covering the orchestrator + receipt write.

## Future work

- Promote `mass_refresh_receipts` into a Windmill schedule (weekly or
  daily) once doctor signals confirm the sweep is stable in
  production.
