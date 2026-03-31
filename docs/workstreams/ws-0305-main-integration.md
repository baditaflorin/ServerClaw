# Workstream ws-0305-main-integration

- ADR: [ADR 0305](../adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- Title: Integrate ADR 0305 k6 exact-main replay onto `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.118
- Platform Version Observed During Integration: 0.130.76
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0305-mainline-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0305-mainline-final`
- Owner: codex
- Depends On: `ws-0305-live-apply`

## Purpose

Carry the verified ADR 0305 branch-local live apply onto the synchronized
`origin/main` baseline, cut release `0.177.118` from that exact-main tree, rerun
the authoritative repository automation and k6 validation paths from committed
source, and publish one canonical mainline receipt that preserves both the
passing smoke path and the truthful non-zero live load failure.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0305-main-integration.md`
- `docs/workstreams/ws-0305-live-apply.md`
- `docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md`
- `docs/runbooks/k6-load-testing.md`
- `docs/runbooks/configure-openfga.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `scripts/workstream_surface_ownership.py`
- `tests/test_workstream_surface_ownership.py`
- `receipts/live-applies/`
- `receipts/k6/`
- `receipts/sbom/`

## Verification

- The exact-main branch refreshed to latest realistic `origin/main` commit `5c7e07235f7b0da1f756148e145397f0ac6ceb10`, which carried repository version `0.177.117` and platform version `0.130.76`; committed source `0d6e8c9eb5d9d086e74cf92d8165248295baa076` was then used as the authoritative replay candidate.
- The first exact-main smoke attempt exposed live drift rather than an ADR 0305 repo regression: Prometheus on `monitoring-lv3` was still loopback-bound to `127.0.0.1:9090` and OpenFGA on `docker-runtime-lv3` was concurrently restarting. The resulting failure is preserved in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r5-0.177.118.txt`.
- `make converge-monitoring` then completed successfully from the rebased tree and updated the Prometheus runtime contract on `monitoring-lv3`; the correction loop is recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-converge-monitoring-r8-0.177.118.txt` and `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-prometheus-bind-manual-r1-0.177.118.txt`.
- The repaired exact-main smoke replay passed from committed source and produced `receipts/k6/smoke-keycloak-20260331T133226Z.json` and `receipts/k6/smoke-openfga-20260331T133226Z.json`, with `110/0` and `112/0` request/failure counts respectively, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r6-0.177.118.txt`.
- The exact-main load replay completed without the earlier NATS deadlock and preserved the truthful final outcome in `receipts/k6/load-keycloak-20260331T133416Z.json`, `receipts/k6/load-openfga-20260331T133416Z.json`, and `receipts/k6/raw/20260331T133416Z-load-summary.json`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-load-r3-0.177.118.txt`. Keycloak failed the declared 1% objective with `1585` requests and `441` failures (`27.82%`); OpenFGA passed the run with `1184` requests and `8` failures (`0.68%`) but still reported `error_budget_remaining_pct: 0.0`.
- The final exact-main load replay also verified the repo automation hardening: controller-local NATS and ntfy publication failures were bounded into warnings instead of blocking or discarding the receipts.
- The final repo-wide validation sweep exposed one integration-time automation contradiction: `scripts/workstream_surface_ownership.py` treated a terminal `live_applied` workstream branch as unownable even when it still declared an ownership manifest. This workstream now hardens that validator, covers the new behavior in `tests/test_workstream_surface_ownership.py`, and records the monitoring replay SBOM receipt under `receipts/sbom/host-monitoring-lv3-2026-03-31.cdx.json`.
- The terminal automation bundle now passes on the `0.177.118` tree: `make remote-validate` passed on `docker-build-lv3`, and `make pre-push-gate` passed after `remote_exec.sh --local-fallback` transparently recovered from transient `502 Bad Gateway` pulls of `registry.lv3.org/check-runner/infra:2026.03.23` during the remote `packer-validate` and `tofu-validate` lanes.
- The canonical mainline receipt for the closeout is `receipts/live-applies/2026-03-31-adr-0305-k6-mainline-live-apply.json`.

## Outcome

- ADR 0305 is fully integrated on the dedicated exact-main branch and included
  in repository release `0.177.118`.
- The canonical closeout receipt is
  `receipts/live-applies/2026-03-31-adr-0305-k6-mainline-live-apply.json`.
- Platform version remains `0.130.76` for this merge because ADR 0305 first
  became true earlier on platform version `0.130.75`; this exact-main closeout
  records the latest-main replay and the hardened repository automation path.
