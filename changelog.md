# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- ADR 0451 + ws-0451: Phase 6 self-healing actions. Three primitives
  that close the doctor → heal loop: registry-driven role lookup in
  `refresh_safe_receipts.py` (consults `platform_service_registry`'s
  `roles:` field before falling back to the heuristic, unblocks the
  safe_to_refresh signal); `scripts/heal.py` + `make heal` orchestrator
  over every doctor heal_command (live: 2 actionable signals);
  `scripts/heal_validator_docstrings.py` synthesises one-line docstrings
  for validators missing one and **healed all 14 in this release**.
  Live `make doctor` drift signals dropped 4/7 → 3/7 non-zero.
  55 new tests (7 + 15 + 33).
- ADR 0450 + ws-0450: Phase 5 self-healing aggregator + post-merge
  rename hook. `scripts/doctor.py` + `make doctor` aggregates every
  Phase-1/2/3/4 drift signal in one command (live: 4/7 non-zero —
  72/187 stale receipts, 3 dangling surfaces, 14 missing validator
  docstrings, 1 .gitkeep substrate placeholder).
  `scripts/heal_workstream_renames.py` + `.githooks/post-merge`
  auto-rewrites `shared_surfaces` paths after merges introduce file
  renames (used during this release to fix 2 real dangling-surface
  workstreams: ws-0377 and ws-0396).
  `config/windmill/schedules/refresh-safe-receipts.yaml` is the
  declarative template for the weekly receipt-refresh cron the next
  production session activates. 39 new tests (18 doctor + 21 rename hook).
- ADR 0449 + ws-0449: Phase 4 self-healing primitives. Three new
  scripts derived from the 2026-04-28 postmortem: `scripts/reserve_adr.py`
  (atomic ADR-number CLI eliminating the collision class that forced
  this very workstream to renumber 0448→0449 mid-session);
  `scripts/generate_validator_catalogue.py` (gate-coverage map at
  `build/validator-catalogue.yaml` — 30 validators surfaced, 18 in
  `validate_repo.sh`, 14 missing docstrings); `scripts/refresh_safe_receipts.py`
  (classifies stale receipts into safe-to-refresh vs needs-review;
  live signal: 11 needs-review against the live stack.yaml).
  Validator-catalogue freshness wired into `validate_repo.sh` as
  advisory `validate_catalogue_freshness`. 60 new tests.

## Latest Release

- [0.179.14 release notes](docs/release-notes/0.179.14.md)

## Previous Releases

- [0.179.13 release notes](docs/release-notes/0.179.13.md)
- [0.179.12 release notes](docs/release-notes/0.179.12.md)
- [0.179.11 release notes](docs/release-notes/0.179.11.md)
- [0.179.10 release notes](docs/release-notes/0.179.10.md)
- [0.179.9 release notes](docs/release-notes/0.179.9.md)
- [0.179.8 release notes](docs/release-notes/0.179.8.md)
- [0.179.7 release notes](docs/release-notes/0.179.7.md)
- [0.179.6 release notes](docs/release-notes/0.179.6.md)
- [0.179.5 release notes](docs/release-notes/0.179.5.md)
- [0.179.4 release notes](docs/release-notes/0.179.4.md)
- [0.179.3 release notes](docs/release-notes/0.179.3.md)
- [0.179.2 release notes](docs/release-notes/0.179.2.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (530 releases)](docs/release-notes/index/2026.md)
