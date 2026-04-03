# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Atlas schema validation, snapshot refresh, and Windmill drift detection latest-main replay
- Status: merged
- Latest Realistic Live Baseline Commit: `e28f1e51729a23c5a3d9b384ec285571a50cfa58`
- Latest Realistic Live Baseline Repo Version: `0.177.142`
- Latest Realistic Live Baseline Platform Version: `0.130.90`
- Final Integrated `origin/main` Head: `9c58e76c652b9d5e65504d44412aad454207bcb8`
- Final Integrated `origin/main` Repo Version: `0.177.147`
- Final Integrated `origin/main` Platform Version: `0.130.92`
- Included In Repo Version: `0.177.148`
- Live Applied In Platform Version: `0.130.90`
- Implemented On: `2026-04-02`
- Branch: `codex/ws-0304-mainline`
- Worktree: `.worktrees/ws-0304-mainline`
- Owner: codex
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0304-atlas-mainline-live-apply.json`

## Outcome

- Rebased the ADR 0304 live-apply branch onto the latest realistic live baseline `e28f1e51` (repo `0.177.142`, platform `0.130.90`) for the replay work, then carried the final repository closeout on top of `origin/main` head `9c58e76c` (repo `0.177.147`, platform `0.130.92`) after the exact-main portal integration releases landed during verification.
- Replayed the dependency chain end to end from the current codebase state: `make converge-step-ca env=production` completed from the realistic live baseline, while `make converge-openbao env=production` and `make converge-windmill env=production` completed after the mainline rebase, confirming that the later integration releases did not change the Atlas/OpenBao/Windmill live paths.
- The replay surfaced three latest-main stability gaps and fixed them in-repo before the final merge: default Docker bridge-chain recovery in `linux_guest_firewall`, retry guards around PostgreSQL pgaudit grant steps, and a localhost Windmill API wait before repo-managed script sync while retaining the stricter runtime env contract gate for consumer startup and recreation.
- Refreshed Atlas snapshots after the live replay and re-verified both the repo-side `atlas-drift-check` path and the seeded `f/lv3/atlas_drift_check` Windmill job clean with `drift_count: 0` and no published notifications across the 20 cataloged PostgreSQL databases.

## Verification

- `make converge-step-ca env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-step-ca-r6-0.177.142.txt`
  Result: the latest realistic live-baseline Step-CA replay passed with final recap `docker-runtime-lv3 : ok=124 changed=1 failed=0`, `proxmox_florin : ok=54 changed=4 failed=0`, and no failed hosts across the remaining guests.
- `make converge-openbao env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-openbao-r4-0.177.142.txt`
  Result: the integrated-main OpenBao replay passed with final recap `docker-runtime-lv3 : ok=381 changed=8 failed=0` and `postgres-lv3 : ok=75 changed=1 failed=0`.
- `make converge-windmill env=production`
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-converge-windmill-r7-0.177.142.txt`
  Result: the integrated-main Windmill replay finished cleanly with final recap `docker-runtime-lv3 : ok=363 changed=48 failed=0`, `postgres-lv3 : ok=92 changed=1 failed=0`, and `proxmox_florin : ok=41 changed=4 failed=0`.
- Repo Atlas automation path
  Evidence:
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-refresh-snapshots-r5-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-validate-r5-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-lint-r4-0.177.142.txt`
  - `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-r5-0.177.142.txt`
  Result: `atlas-refresh-snapshots`, `atlas-validate`, `atlas-lint`, and the repo-side `atlas-drift-check` all passed from the rebased tree with `drift_count: 0`, no drift receipts, and no NATS or ntfy notifications.
- Seeded Windmill Atlas drift job
  Evidence: `receipts/live-applies/evidence/2026-04-02-ws-0304-mainline-atlas-drift-check-seeded-r5-0.177.142.txt`
  Result: the seeded `f/lv3/atlas_drift_check` job returned `returncode: 0`, `report.status: clean`, `drift_count: 0`, and no published notifications across the 20 cataloged PostgreSQL databases.
- Targeted latest-main regression slice
  Evidence: `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-targeted-pytest-r5-0.177.148.txt`
  Result: the targeted latest-main regression slice re-passed from the final release-cut tree covering the firewall, PostgreSQL, Windmill runtime, OpenBao runtime helpers, validation-gate contracts, and compose-runtime regression tests.
- Targeted repository validation and closeout gates
  Evidence:
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-validation-runner-contracts-validate-r5-0.177.148.txt`
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-generated-docs-r3-0.177.148.txt`
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-agent-standards-r5-0.177.148.txt`
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-diff-check-r4-0.177.148.txt`
  Result: the release-cut tree validated cleanly after rebasing onto `9c58e76c`, including runner-contract validation, generated-doc freshness after regenerating the ADR index, canonical truth, status docs, the platform manifest, and the shared architecture-diagram bundle, `agent-standards`, and a final whitespace/conflict-marker check before the mainline push.
- Governed validation automation lanes
  Evidence:
  - `receipts/live-applies/evidence/2026-04-03-ws-0304-mainline-remote-validate-r1-0.177.148.txt`
  Result: the 2026-04-03 controller-local fallback replay captured the current governed remote-validation state from the rebased tree while the final clean remote-validation and pre-push-gate reruns were still pending before merge-to-main.

## Merge Notes

- This workstream became the final integration step on top of `9c58e76c`, so the protected release and canonical-truth files were updated here for release `0.177.148`: `VERSION`, `RELEASE.md`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.148.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `README.md`, `workstreams.yaml`, and the ADR/workstream state while restoring the historical `docs/release-notes/0.177.144.md` content from `origin/main`.
- The combined proof set is authoritative because the later exact-main portal releases changed shared release, docs, and canonical-truth surfaces but did not change the Atlas, OpenBao, or Windmill live-apply automation path; the Step-CA replay from `e28f1e51` and the later OpenBao, Windmill, Atlas, and release-cut validation replays from the rebased tree all remained consistent.
- The canonical receipt id reserved for `versions/stack.yaml` and `workstreams.yaml` is `2026-04-02-adr-0304-atlas-mainline-live-apply`.
