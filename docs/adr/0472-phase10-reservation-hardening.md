# ADR 0472: Phase 10 — Fix ADR-Collision Class via Early-Merge Reservation

- Status: Proposed
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-29
- Concern: agent-coordination, drift, multi-agent-races
- Tags: adr-reservation, collision-prevention, fast-merge, ci-gate
- Reservation: res-0472-phase-10-fix-adr-collision-class-via-ear
- Implements: Phase 10 of the postmortem self-healing roadmap
- Depends on:
  - ADR 0325 (ADR Discovery & Reservation Ledger)
  - ADR 0449 (Phase 4 reserve_adr.py)

---

## Context

Phase 9 (ADR 0465) renumbered its ADR **four times** mid-session
(0462 → 0463 → 0464 → 0465) because origin shipped a different ADR
under each successive number while my PR was open. Phase 4's
`reserve_adr.py --reserve` writes a reservation entry to a local
`docs/adr/index/reservations.yaml`, but that entry only protects
against collision once committed to `main`. When the reservation
sits in a long-lived feature-branch PR, other agents claim the same
number from main with no awareness of the local reservation.

The session's failure pattern:

1. Agent A: `reserve_adr.py --reserve` writes 0464 reservation locally.
2. Agent A: opens 50-line ADR draft + dependent code; PR opens.
3. Agent B (parallel): `reserve_adr.py --next` reads main (no
   reservation there), gets 0464, ships PR, merges.
4. Agent A's PR rebase fails — 0464 is now claimed.
5. Agent A renumbers to 0465, repeats.

Phase 10 closes this loop.

---

## Decision

### Phase 10.1 — `make reserve-adr-pr`

A new Make target that:

1. Computes the next free ADR number via `reserve_adr.py --next`.
2. Opens a tiny single-commit branch (`reservation/<number>`) whose
   only diff is the new entry in `docs/adr/index/reservations.yaml`.
3. Pushes the branch, opens a PR, auto-merges via `gh pr merge --auto`
   (or `--squash --auto`).
4. Once merged on main, the reservation is the canonical source of
   truth — any other agent running `--next` will see the number as
   taken.
5. Returns the reserved number on stdout for the calling agent's
   subsequent work.

The whole flow is < 30 seconds end-to-end and atomic from the
caller's perspective.

### Phase 10.2 — CI gate: unreserved-ADR rejection

A new validator `scripts/validate_adr_reservation.py`:

- Walks every `docs/adr/04*.md` added by the PR.
- Cross-references each new number against `reservations.yaml`
  on `origin/main`.
- Fails the gate when the PR adds an ADR whose number was never
  reserved on main.

Wired into `validate_repo.sh` as `validate_adr_reservation` (advisory
initially; promoted to required after one clean session per the
ADR 0460 promotion-tracker pattern).

### Phase 10.3 — `scripts/reserve_adr.py --release`

After the ADR file lands on main, the reservation is satisfied and
the entry should be cleared so the ledger doesn't accumulate
stale records. `--release <number>` removes the matching entry, run
from the release commit that lands the ADR.

Phase 10.4 (deferred): integrate `--release` into the existing
release-notes generator so the cleanup happens automatically.

---

## Acceptance Criteria

- `make reserve-adr-pr reason="<X>"` reserves an ADR number via a
  fast-merged single-commit PR; returns the number on stdout.
- `scripts/validate_adr_reservation.py` fails when a PR adds an ADR
  not present in main's `reservations.yaml`; passes when present.
- `scripts/reserve_adr.py --release <N>` removes the matching
  reservation entry; idempotent.
- Tests cover plan synthesis, gate-rejection happy path, and
  --release idempotence.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | 10.1 — `make reserve-adr-pr` | 0.179.x |
| 2 | 10.2 — `validate_adr_reservation.py` (advisory) | 0.179.x |
| 3 | 10.3 — `--release` flag | 0.179.x |
| 4 | (deferred) auto-release in generate_release_notes | phase 11 |

---

## References

- Phase 9 ADR-collision retrospective (4 renumbers in one session)
- ADR 0449 — `reserve_adr.py` shipped in Phase 4
- ADR 0325 — Reservation ledger originator
