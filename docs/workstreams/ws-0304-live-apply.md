# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Atlas schema validation, snapshot refresh, and Windmill drift detection exact-main replay
- Status: live_applied
- Exact-main Baseline Commit: `67bc9f13f973f5386b1ec5b4dd4304e400c214a8`
- Exact-main Baseline Repo Version: `0.177.142`
- Exact-main Baseline Platform Version: `0.130.89`
- Included In Repo Version: `0.177.143`
- Live Applied In Platform Version: `0.130.90`
- Implemented On: `2026-04-02`
- Branch: `codex/ws-0304-mainline`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0304-mainline`
- Owner: codex
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0304-atlas-mainline-live-apply.json`

## Outcome

- Rebased the ADR 0304 live-apply branch onto the latest realistic
  `origin/main` baseline (`67bc9f13`) before the final replay and kept the
  protected integration files untouched until the exact-main release step.
- Replayed the current-main dependency chain end to end:
  `make converge-step-ca env=production`, `make converge-openbao env=production`,
  and `make converge-windmill env=production` all completed successfully from
  the rebased tree before the final release surfaces were cut.
- The exact-main replay surfaced three current-main stability gaps and fixed
  them in-repo before the final merge:
  default Docker bridge-chain recovery in `linux_guest_firewall`, retry guards
  around PostgreSQL pgaudit grant steps, and a localhost Windmill API wait
  before repo-managed script sync while retaining the stricter runtime env
  contract gate for consumer startup and recreation.
- Refreshed Atlas snapshots after the live replay and re-verified both the
  repo-side `atlas-drift-check` path and the seeded
  `f/lv3/atlas_drift_check` Windmill job clean with `drift_count: 0` and no
  published notifications across the 20 cataloged PostgreSQL databases.

## Verification

- `make converge-step-ca env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-step-ca-r4-0.177.142.txt`
  Result: the current-main step-ca replay passed with final recap
  `docker-runtime-lv3 : ok=144 changed=2 failed=0 rescued=1`,
  `proxmox_florin : ok=54 changed=4 failed=0`, and no failed hosts.
- `make converge-openbao env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-openbao-r3-0.177.142.txt`
  Result: the current-main OpenBao replay passed with final recap
  `docker-runtime-lv3 : ok=381 changed=8 failed=0` and
  `postgres-lv3 : ok=75 changed=1 failed=0`.
- `make converge-windmill env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-windmill-r6-0.177.142.txt`
  Result: the current-main Windmill replay finished cleanly after the exact-main
  recovery fixes with final recap
  `docker-runtime-lv3 : ok=364 changed=47 failed=0 rescued=0`,
  `postgres-lv3 : ok=95 changed=6 failed=0`,
  `proxmox_florin : ok=41 changed=4 failed=0`.
- Repo Atlas automation path
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-refresh-snapshots-r4-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-validate-r4-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-lint-r3-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-r4-0.177.142.txt`
  Result: `atlas-refresh-snapshots`, `atlas-validate`, `atlas-lint`, and the
  repo-side `atlas-drift-check` all passed from the rebased tree with
  `drift_count: 0`, no drift receipts, and no NATS or ntfy notifications.
- Seeded Windmill Atlas drift job
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-seeded-r4-0.177.142.txt`
  Result: `status: ok`, `report.status: clean`, `drift_count: 0`, and no
  published notifications across the 20 cataloged PostgreSQL databases.
- Targeted latest-main regression slice
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-targeted-pytest-r3-0.177.142.txt`
  Result: `44 passed in 1.20s` covering the latest-main firewall, PostgreSQL,
  Windmill runtime, and compose-runtime regression tests.
- Targeted repository validation and closeout gates
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-validation-runner-contracts-validate-r3-0.177.143.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-generated-docs-r1-0.177.143.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-agent-standards-r3-0.177.143.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-diff-check-r2-0.177.143.txt`
  Result: the release-cut tree validated cleanly, including runner contract
  validation, generated-doc freshness after regenerating the ADR index,
  canonical truth, platform manifest, and shared diagrams, `agent-standards`,
  and a final whitespace/conflict-marker check before the mainline push.

## Merge Notes

- This workstream became the exact mainline integration step, so the protected
  release and canonical-truth files were updated here after live verification:
  `VERSION`, `RELEASE.md`, `changelog.md`, `docs/release-notes/README.md`,
  `docs/release-notes/0.177.143.md`, `versions/stack.yaml`,
  `build/platform-manifest.json`, `README.md`, `workstreams.yaml`, and the
  ADR/runbook state.
- The canonical receipt id reserved for `versions/stack.yaml` and
  `workstreams.yaml` is `2026-04-02-adr-0304-atlas-mainline-live-apply`.
