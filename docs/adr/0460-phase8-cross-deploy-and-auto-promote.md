# ADR 0460: Phase 8 — Cross-Deployment Doctor + Advisory Auto-Promotion

- Status: Proposed
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-29
- Concern: self-healing, multi-deployment-safety, gate-enforcement, drift
- Tags: doctor, cross-deployment, advisory, promotion, auto-graduation
- Reservation: res-0460-phase-8-cross-deploy-auto-promote (atomic via reserve_adr.py)
- Implements: postmortem 2026-04-28 self-healing roadmap — Options B + C
- Depends on:
  - ADR 0450 (Phase 5 doctor + post-merge hook)
  - ADR 0451 (Phase 6 self-healing actions)
  - ADR 0455 (Phase 7 drive doctor signals to zero) — predecessor
  - ADR 0439 (Multi-Deployment Repo Architecture)
  - ADR 0456 (Deployment-Aware Cert Validation)

---

## Context

Phase 7 drove the local-repo doctor signal from 3/7 → 1/7 non-zero.
Two structural follow-ups remain, both addressed here:

**Option B — Cross-deployment doctor (multi-deployment visibility).**
Right now `make doctor` only inspects the local checkout. Two
deployments (lv3.org + 0fork.com) sharing one codebase but diverging
in `live_apply_evidence` and per-deployment overlays are invisible to
the gate. ADR 0456 (deployment-aware cert validation) and ADR 0459
(deployment-lifecycle CLI parity) shipped per-deployment infra
without a corresponding observability surface.

**Option C — Advisory auto-promotion.**
The session-running pattern of "wire it as advisory, never promote"
leaves drift surfaces optional indefinitely. Three signals have been
clean for multiple consecutive sessions:

- `validate_no_hardcoded_topology --rule late_bound_default` — clean
  since Phase 1.3 (5 sessions).
- `validate_catalogue_freshness` — clean since Phase 6.3 (3 sessions).
- `validate_traceability` — clean since Phase 7 (2 sessions).

A promotion tracker that consumes a per-gate-run ledger and surfaces
"eligible for promotion" closes the loop the postmortem opened
(item A8).

---

## Decision

### Phase 8.1 (Option C) — Promotion tracker + receipts ledger

A new `receipts/gate-runs/` ledger captures per-run gate outcomes:

```yaml
gate: validate_no_hardcoded_topology
rule: late_bound_default
ran_on: 2026-04-29T08:14:00Z
result: clean       # or "findings" or "errored"
finding_count: 0
session_id: ws-0460-phase8
mode: advisory      # or "required"
```

`scripts/promotion_tracker.py`:

1. Reads the most recent N (default 5) ledger entries per
   `<gate, rule>` tuple.
2. Reports each gate as `eligible` (last 3+ runs clean), `streaking`
   (1-2 clean runs in a row), or `unstable` (any non-clean run in
   the window).
3. Default mode prints a summary; `--json` for ops_portal; `--apply`
   would (deferred) flip the gate's wiring from advisory to
   required, but that's a follow-up — this ADR ships only the
   tracker + a manual promotion playbook.

Wired into `make doctor` as a new `[promotion_eligible]` informational
row that surfaces the eligible-for-promotion gates without blocking.

### Phase 8.2 (Option B) — Cross-deployment doctor

Two layers, only the first lands here:

- **`scripts/cross_deployment_doctor.py`** — reads each deployment
  under `.local/deployments/<slug>/state/` (the static side that's
  reachable from any worktree) and synthesises a `deployment_drift`
  signal: per-receipt date skew between deployments, per-service
  presence skew (running on lv3 but not 0fork, etc.). Output mirrors
  `doctor.py`'s human + JSON shapes.
- **Live probe via SSH** (deferred) — would require operator runtime
  access; out of scope this session.

`make doctor deployment=<slug>` becomes a new entry point that runs
the full local doctor PLUS the cross-deployment subset filtered to
that deployment's view. With no `deployment=` arg, the existing
behaviour is preserved.

---

## Acceptance Criteria

- `scripts/promotion_tracker.py --list` prints at least the three
  pre-existing-clean gates as `eligible` against synthetic ledger
  fixtures.
- `scripts/cross_deployment_doctor.py` runs against
  `.local/deployments/` and reports per-deployment drift (or "no
  deployments configured" when the directory is missing).
- `receipts/gate-runs/` is committed with a README documenting the
  schema; one synthetic example.
- `make doctor` integrates the new `[promotion_eligible]` row.
- Tests cover: ledger parsing, eligibility classification, drift
  computation against synthetic deployment trees.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | 8.1 — promotion tracker + ledger schema | 0.179.x |
| 2 | 8.2 — cross_deployment_doctor.py + tests | 0.179.x |
| 3 | 8.3 — wire into `make doctor` | 0.179.x |
| 4 | (deferred) advisory→required `--apply` flag | phase 9 |
| 5 | (deferred) live SSH probe layer | phase 9 |

---

## References

- Postmortem 2026-04-28
- ADR 0455 — Phase 7 drive doctor signals to zero (predecessor)
- ADR 0456 — Deployment-aware certificate validation (sibling)
- ADR 0459 — Deployment-lifecycle CLI parity (sibling)
