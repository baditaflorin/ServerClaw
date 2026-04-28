# ADR 0450: Phase 5 — `make doctor` Aggregator + Post-Merge Rename Hook

- Status: Proposed
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-28
- Concern: self-healing, automation, agent-coordination, drift, debuggability
- Tags: doctor, post-merge, rename, windmill, scheduled-refresh
- Implements: postmortem 2026-04-28 self-healing roadmap items A1, A6, A4-cron
- Depends on:
  - ADR 0445 (Phase 1 multi-deployment hardening) — receipt + traceability surfaces
  - ADR 0446 (Phase 2 receipt freshness) — `check_receipt_freshness.py`
  - ADR 0447 (Phase 3 LLM ergonomics + traceability) — `generate_traceability.py`
  - ADR 0449 (Phase 4 self-healing primitives) — `reserve_adr.py`,
    `generate_validator_catalogue.py`, `refresh_safe_receipts.py`

---

## Context

Phase 4 (ADR 0449) shipped three primitives — receipt classifier, validator
catalogue generator, ADR-number reserver — but each one has its own CLI.
A fresh agent opening a worktree has no single "what's drifting?"
view; they must remember to run each script individually.

Phase 4's deferred items also included:

- **A1 — `make doctor`**: aggregator across every Phase-1/2/3/4 drift
  signal so an operator gets the full picture in one command.
- **A6 — post-merge rename hook**: 3 of the dangling-shared-surface
  signals from ws-0447 traceability come from file renames in agent
  A's PR leaving agent B's workstream YAML pointing at a dead path.
  An auto-rewrite hook closes that class without operator intervention.
- **A4 — Windmill schedule for receipt refresh**: the production
  recurring task that runs `refresh_safe_receipts.py --apply` on a
  weekly cadence.

Phase 5 ships all three. The first two are shippable from any worktree;
the third lands as a committed Windmill template that the next
production-access session activates.

---

## Decision

### A1 — `scripts/doctor.py` + `make doctor`

A single aggregator that runs every drift signal currently surfaced
through `validate_repo.sh`, parses each result, and emits a
human-readable summary plus a structured `--json` view:

```
$ make doctor
[stale receipts]    72/186 stale at 30d window
[dangling surfaces] 3 workstreams have surfaces that don't exist on disk
[validator gaps]    14 validators missing docstrings, 18 lack ADR refs
[unreserved adrs]   0 ADRs on disk are unreserved (clean)
[blocked substrate] 1 path under collections/.../molecule/ is .gitkeep
```

Each row maps to either a `make heal-X` companion (the action) or a
`make explain-X` companion (the deeper view). Phase 5 wires the
explain side; the heal side lands incrementally as each signal
acquires a safe automated fix.

### A6 — `.githooks/post-merge` + `scripts/heal_workstream_renames.py`

When `git merge` (including squash-merge fast-forwards) introduces
file renames, the post-merge hook scans every workstream YAML's
`shared_surfaces` for paths that match the old names. Found matches
are automatically rewritten to the new path; the operator gets a
`[heal-renames] N path(s) updated in M workstream(s)` notice. The
rewrite happens to the working tree but does NOT auto-commit — the
operator decides whether to fold it into their next commit or open
a dedicated `[heal-renames]` PR.

The heuristic is conservative: only exact-match string substitution
on rename pairs `git diff` reports as `--diff-filter=R`. It does not
attempt fuzzy matches, glob substitutions, or path-component edits.

### A4-cron — Windmill schedule template

A committed YAML template under `config/windmill/schedules/` that the
next production session imports. The template targets
`refresh_safe_receipts.py` on a weekly cadence with `--apply` plus the
notification wiring (Plane issue creation when needs-review > 0). Not
activated this session — needs SSH access this worktree doesn't have.

---

## Acceptance Criteria

- `python3 scripts/doctor.py` runs against the live repo and reports
  every Phase-1/2/3/4 drift signal in <10 seconds.
- `make doctor` is a thin wrapper over the script; works from any
  worktree.
- `.githooks/post-merge` exists, is executable, and is exercised by a
  unit test that mocks `git diff --diff-filter=R` output.
- `scripts/heal_workstream_renames.py` rewrites matched paths in
  workstream YAMLs without removing surrounding content.
- `config/windmill/schedules/refresh-safe-receipts.yaml` exists and
  passes the existing Windmill schedule schema validation.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | `scripts/doctor.py` + Makefile target | 0.179.x |
| 2 | `.githooks/post-merge` + `scripts/heal_workstream_renames.py` | 0.179.x |
| 3 | `config/windmill/schedules/refresh-safe-receipts.yaml` (template) | 0.179.x |
| 4 | (deferred to operator) Windmill schedule activation in production | — |

---

## References

- Postmortem 2026-04-28 — multi-deployment hardening three-phase session
- ADR 0449 — Phase 4 self-healing primitives (predecessor)
- ADR 0447 — traceability validator (consumed by `doctor.py`)
- ADR 0446 — receipt freshness checker (consumed by `doctor.py`)
