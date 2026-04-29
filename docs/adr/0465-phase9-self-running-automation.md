# ADR 0465: Phase 9 — Self-Running Automation Primitives

- Status: Proposed
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-29
- Concern: self-healing, automation, token-efficiency, agent-coordination
- Tags: doctor, snapshot, auto-promote, regression-watcher, daily-heal
- Reservation: res-0465-phase-9-self-running-automation-primitiv
- Implements: 4 of the 10 token-saving / self-running items from
  the 2026-04-29 review
- Depends on:
  - ADR 0450 (Phase 5 doctor + post-merge hook)
  - ADR 0451 (Phase 6 self-healing actions)
  - ADR 0455 (Phase 7 drive doctor signals to zero)
  - ADR 0460 (Phase 8 cross-deploy + auto-promote tracker)

---

## Context

Phase 8 shipped two new probes (`promotion_eligible`,
`cross_deployment_drift`) and the `promotion_tracker.py` read-only
classifier. Four follow-ups from the "10 token-saving / self-running"
review are CPU-only, no LLM in the loop, and shippable from this
worktree. Phase 9 implements them.

The pattern across all four: turn an LLM-orchestrated read or fix
loop into a deterministic file or scheduled job. Agents go from
"run doctor → read 9 probe outputs → decide → run heal → re-check"
to "read one cached file → done."

---

## Decision

### Phase 9.1 — Cached `make doctor --json` snapshot (item 1)

`scripts/doctor.py` gains a `--snapshot` mode that runs every probe
exactly once and writes `build/doctor-snapshot.json`. A new
`probe_doctor_snapshot_freshness` reads the snapshot's mtime against
the current git HEAD and reports whether it's fresh; agents reading
the snapshot file (cheap) instead of running the full probe set
(forks 9 subprocesses) save significant tokens.

A `pre-commit` hook refreshes the snapshot when commit-time work
makes the prior view stale. Stale-snapshot behaviour is graceful —
the freshness probe surfaces it as `[!]` so the agent knows to
re-run, but the snapshot file is still readable.

### Phase 9.2 — `scripts/apply_promotion.py` (item 7)

Phase 8's `promotion_tracker.py` is read-only. This script consumes
the tracker's `--json` output, identifies gates marked `eligible`,
and emits a structured promotion plan: which `validate_repo.sh`
function to flip, what `mode: required` ledger entry to seed.

`--apply` mode rewrites the targeted line in `validate_repo.sh`
(advisory wording → required wording) and seeds a `mode: required`
gate-run entry so the tracker reclassifies the gate as `promoted`.

Default dry-run mode prints the proposed edits without touching the
file — same gesture as the rest of the heal toolkit.

### Phase 9.3 — `scripts/doctor_regression_watch.py` + Windmill schedule (item 10)

Compares the live `make doctor --json` output against a baseline
(`receipts/doctor-baselines/<sha>.json`) and reports any signal
that flipped from `[ok]` to `[!]`. New regressions emit a
machine-readable issue payload that a Windmill schedule can post to
Plane. Defaults: hourly cadence, baseline = the latest
`receipts/doctor-baselines/` entry whose sha is reachable from
`origin/main`.

Schedule template lands at `config/windmill/schedules/doctor-regression-watch.yaml`.
Activation deferred to operator with Windmill access (same pattern as ADR 0450).

### Phase 9.4 — Daily `make heal --apply` Windmill schedule (item 6)

A second template under `config/windmill/schedules/daily-heal-apply.yaml`
that runs `make heal --apply` at 03:00 UTC every day. The heal
orchestrator is already idempotent and dry-run safe; daily runs
opportunistically converge anything safe-to-fix without operator
intervention.

---

## Acceptance Criteria

- `scripts/doctor.py --snapshot` writes `build/doctor-snapshot.json`
  with the same shape as `--json` plus a `generated_at` and
  `head_sha` envelope.
- `make doctor` gains a 10th probe (`doctor_snapshot_freshness`) that
  reports the snapshot's mtime vs git HEAD.
- `scripts/apply_promotion.py --json` emits a plan listing eligible
  gates and the proposed `validate_repo.sh` edits.
- `scripts/doctor_regression_watch.py` exits 0 when no regressions,
  1 when at least one signal regressed.
- Two committed Windmill schedule templates under
  `config/windmill/schedules/`.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | 9.1 — doctor snapshot + freshness probe | 0.179.x |
| 2 | 9.2 — apply_promotion.py | 0.179.x |
| 3 | 9.3 — doctor_regression_watch.py + schedule template | 0.179.x |
| 4 | 9.4 — daily heal-apply schedule template | 0.179.x |
| 5 | (deferred) operator activates schedules in Windmill | — |
| 6 | (deferred) items 2/3/5/8/9 from the 10-item review | phase 10 |

---

## References

- 10 token-saving / self-running review (2026-04-29)
- ADR 0460 — Phase 8 cross-deploy + promotion tracker
- ADR 0450 — Windmill schedule template pattern
