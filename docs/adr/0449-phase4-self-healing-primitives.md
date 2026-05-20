# ADR 0449: Phase 4 Self-Healing Primitives

- Status: Proposed
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-28
- Concern: self-healing, automation, drift, programmability, agent-coordination
- Tags: adr-reservation, validator-catalogue, receipt-refresh, doctor
- Implements: subset of [self-healing roadmap, postmortem 2026-04-28]
- Depends on:
  - ADR 0325 (ADR Discovery & Reservation Ledger) — substrate exists
  - ADR 0445/0446/0447 (Phase 1/2/3 multi-deployment hardening) — predecessors

---

## Context

The 2026-04-28 postmortem
([../postmortems/2026-04-28-multi-deployment-hardening-three-phase-session.md](../postmortems/2026-04-28-multi-deployment-hardening-three-phase-session.md))
identified four classes of repeatable failure in agent-driven hardening
work:

1. **ADR number collision** — concurrent agents picking the same number
   on local branches without checking origin.
2. **Underestimated existing validator coverage** — review reports
   propose work that's already shipped because nobody greps the
   validator catalogue first.
3. **Receipt staleness invisible until a 502** — `validate_receipt_freshness`
   surfaces 72/186 stale receipts; nothing automatically refreshes them.
4. **Workstream surface drift after renames** — file rename in agent A's
   PR leaves agent B's `shared_surfaces` pointing at a dead path.

Phases 1–3 surfaced the *signals*; Phase 4 turns them into
*self-healing primitives*. The postmortem's "make doctor" North Star is
the combined target — one command tells an operator what's drifting and
offers to fix it.

---

## Decision

Three deliverables in this ADR; two more (A6 post-merge rename hook,
A1 `make doctor`) deferred to phase 5 / 6.

### A2 — `scripts/reserve_adr.py` + atomic reservation

A CLI that:

1. Fetches origin/main (refuses to run on a stale local checkout).
2. Reads `docs/adr/index/reservations.yaml` AND scans `docs/adr/04*.md`
   on origin/main for the highest existing number.
3. Returns the next free number, optionally writing a reservation entry
   keyed on `workstream_id` + `reserved_by` + `expires_on` (default 30d).
4. `--write` mode generates an ADR stub at the right path with the
   reserved number in the title.

This eliminates the ADR 0444→0445 collision class by construction. The
existing `reservations.yaml` ledger (ADR 0325) is the substrate; this
ADR adds the missing CLI on top.

**Tests:** parametrised over (existing-on-disk × existing-in-ledger × race
scenarios). No write side-effects — `--write` is mockable via `--root`.

### A5 — `scripts/generate_validator_catalogue.py`

A generator that:

1. Walks `scripts/validate_*.py` and extracts the docstring's first
   line + any `# ADR:` reference + entry-point function name.
2. Cross-references against `scripts/validate_repo.sh` to mark each
   validator as `runs_in_pre_push: bool`, `runs_in_ci: bool`,
   `target_in_validate_repo_sh: str | null`.
3. Emits `build/validator-catalogue.yaml` with a row per validator.

The output answers "what does the gate currently catch?" in one
file. An LLM authoring a new "we should validate X" review reads this
first; if X is already covered, the review proposes "promote to
required" or "extend coverage" instead of "add new validator."

Wired into `validate_repo.sh` as `validate_catalogue_freshness` (advisory):
re-runs the generator and fails on diff vs. on-disk.

### A4 — `scripts/refresh_safe_receipts.py` (partial)

The full receipt-driven re-converge cron (postmortem item A4) needs
Windmill scheduling and SSH access this worktree doesn't have. This
ADR ships the **safe-refresh helper** — the deterministic part:

1. Loads stale receipts via the existing
   `scripts/check_receipt_freshness.py` machinery.
2. For each stale service, queries `git log` to determine if the
   role has changed since the receipt date.
3. Classifies each into:
   - `safe_to_refresh` — receipt stale but role unchanged (no-op
     converge would just refresh the date)
   - `needs_review` — receipt stale AND role changed (real work)
   - `unknown` — receipt date unparseable
4. Emits a JSON report and (with `--apply`) writes a
   `[receipt-refresh]` commit updating `versions/stack.yaml` for the
   safe-to-refresh set.

The Windmill schedule that calls this in production is deferred to
phase 5; the helper itself is shippable today and runnable manually.

**Live signal expectation:** of the 72 currently-stale receipts, the
helper should classify a non-trivial subset as `safe_to_refresh` —
exactly the case where running a converge would be a no-op except for
the date update. Operators can then run a single command to clear the
backlog.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | `scripts/reserve_adr.py` + tests | 0.179.x |
| 2 | `scripts/generate_validator_catalogue.py` + tests + advisory gate | 0.179.x |
| 3 | `scripts/refresh_safe_receipts.py` + tests (no `--apply` execution this release) | 0.179.x |
| 4 | (deferred) Windmill schedule for receipt refresh | phase 5 |
| 5 | (deferred) post-merge rename hook | phase 5 |
| 6 | (deferred) `make doctor` aggregator | phase 6 |

---

## Acceptance Criteria

- `python3 scripts/reserve_adr.py --next` returns the highest ADR
  number currently on disk + 1, refusing to run if local
  `docs/adr/04*.md` differs from origin/main.
- `python3 scripts/generate_validator_catalogue.py --write` produces
  `build/validator-catalogue.yaml` with at least 25 validators
  catalogued, each with a one-line description.
- `python3 scripts/refresh_safe_receipts.py --json` emits the
  classification report; `--apply` (manual run) writes a
  `[receipt-refresh]` commit for any `safe_to_refresh` entries.

---

## References

- Postmortem 2026-04-28 — multi-deployment hardening three-phase session
- ADR 0325 — ADR Discovery & Reservation Ledger
- ADR 0446 — receipt-freshness checker (this ADR builds on it)
