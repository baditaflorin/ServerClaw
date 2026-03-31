# Workstream ws-0305-live-apply: Live Apply ADR 0305 From Latest `origin/main`

- ADR: [ADR 0305](../adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- Title: Live apply k6 smoke, load, and soak validation with Prometheus remote-write, Windmill schedules, and promotion-gate burn checks from latest `origin/main`
- Status: ready_to_merge
- Live Applied On: 2026-03-31
- Platform Version Observed During Live Apply: 0.130.75
- Branch: `codex/ws-0305-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0305-live-apply`
- Owner: codex
- Depends On: `adr-0096-slo-tracking`, `adr-0119-budgeted-workflow-scheduler`, `adr-0123-service-uptime-contracts-and-monitor-backed-health`, `adr-0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization`, `adr-0276-nats-jetstream-as-the-platform-event-bus`, `adr-0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer`, `adr-0299-ntfy-as-the-push-notification-channel`, `adr-0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0305-live-apply.md`, `docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md`, `docs/runbooks/k6-load-testing.md`, `docs/runbooks/configure-openfga.md`, `docs/schema/k6-receipt.schema.json`, `docs/schema/capacity-model.schema.json`, `Makefile`, `.gitea/workflows/validate.yml`, `config/image-catalog.json`, `config/capacity-model.json`, `config/k6/scripts/http-slo-probe.js`, `config/service-capability-catalog.json`, `config/slo-catalog.json`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/grafana/dashboards/slo-overview.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/control-plane-lanes.json`, `config/api-publication.json`, `config/event-taxonomy.yaml`, `config/ntfy/server.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/openfga.yml`, `scripts/generate_platform_vars.py`, `scripts/k6_load_testing.py`, `scripts/capacity_report.py`, `scripts/promotion_pipeline.py`, `scripts/serverclaw_authz.py`, `scripts/slo_tracking.py`, `scripts/validate_nats_topics.py`, `scripts/validate_repository_data_models.py`, `platform/slo.py`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/**`, `collections/ansible_collections/lv3/platform/roles/proxmox_network/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/**`, `config/windmill/scripts/k6-load-testing.py`, `docs/site-generated/architecture/dependency-graph.md`, `tests/test_k6_load_testing.py`, `tests/test_k6_load_testing_windmill.py`, `tests/test_gitea_workflows.py`, `tests/test_capacity_report.py`, `tests/test_monitoring_vm_role.py`, `tests/test_openfga_metadata.py`, `tests/test_openfga_runtime_role.py`, `tests/test_proxmox_network_role.py`, `tests/test_published_artifact_secret_scan.py`, `tests/test_serverclaw_authz.py`, `tests/test_windmill_default_operations_surface.py`, `tests/test_windmill_operator_admin_app.py`, `tests/test_promotion_pipeline.py`, `tests/test_slo_tracking.py`, `tests/unit/test_event_taxonomy.py`, `receipts/image-scans/2026-03-31-k6-runtime.json`, `receipts/image-scans/2026-03-31-k6-runtime.trivy.json`, `receipts/k6/`, `receipts/live-applies/`

## Scope

- pin the `k6_runtime` container image and record a real Trivy scan receipt
- wire the repo-managed smoke, load, and soak entrypoints into Windmill, SLO tracking, promotion gates, and the private Gitea validation path
- replay the monitoring and Windmill runtime changes live, then capture end-to-end evidence from real k6 runs and the repo automation bundle

## Non-Goals

- changing `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` before the final verified mainline integration step
- widening ADR 0305 beyond the HTTP SLO services currently modeled in `config/slo-catalog.json` and `config/capacity-model.json`
- treating the public GitHub mirror as the authoritative smoke gate for private SLO probes

## Expected Repo Surfaces

- `config/image-catalog.json`
- `config/capacity-model.json`
- `config/k6/scripts/http-slo-probe.js`
- `config/service-capability-catalog.json`
- `config/slo-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/grafana/dashboards/slo-overview.json`
- `receipts/image-scans/2026-03-31-k6-runtime.json`
- `receipts/image-scans/2026-03-31-k6-runtime.trivy.json`
- `.gitea/workflows/validate.yml`
- `scripts/k6_load_testing.py`
- `scripts/capacity_report.py`
- `scripts/slo_tracking.py`
- `scripts/promotion_pipeline.py`
- `playbooks/openfga.yml`
- `scripts/serverclaw_authz.py`
- `collections/ansible_collections/lv3/platform/roles/proxmox_network/tasks/main.yml`
- `platform/slo.py`
- `docs/runbooks/k6-load-testing.md`
- `docs/runbooks/configure-openfga.md`
- `workstreams.yaml`
- `docs/workstreams/ws-0305-live-apply.md`

## Expected Live Surfaces

- `docker-build-lv3` can run the pinned `k6_runtime` smoke gate against Keycloak and OpenFGA while remote-writing into Prometheus on `monitoring-lv3`
- `docker-runtime-lv3` seeds `f/lv3/k6_load_testing`, `f/lv3/k6_load_weekly`, and `f/lv3/k6_soak_monthly` through the Windmill replay
- `monitoring-lv3` listens on the private Prometheus address needed by the build host and Windmill worker
- `docker-runtime-lv3` unseals the Windmill/OpenBao helper path without requiring a full quorum on every compose-env or credentials render

## Ownership Notes

- `workstreams.yaml` and `docs/adr/.index.yaml` remain shared-contract surfaces and must be updated in a merge-safe way.
- The image-scan receipt, the workstream note, and the live-apply evidence files are branch-local exclusive surfaces for this workstream.
- Protected integration surfaces stay out of scope here until the exact-main replay is complete and verified.

## Verification

- Local Trivy scanning of `docker.io/grafana/k6:1.7.1@sha256:44bd1d66c2b019327991b95459d78402b0a7a0a055ab52ee088deea1a044e8d5` returned `critical=0` and `high=1`, recorded in `receipts/image-scans/2026-03-31-k6-runtime.json` with the raw report beside it.
- The focused repository slice covering the k6 runner and remote build gateway now passes after the live-apply fixes:
  `uv run --with pytest python -m pytest -q tests/test_k6_load_testing.py tests/test_remote_exec.py`
  returned `24 passed`, and `bash -n scripts/remote_exec.sh` plus
  `python3 -m py_compile scripts/k6_load_testing.py` both passed from this worktree.
- `make converge-monitoring` now completes successfully from this worktree after the lane-map repair and the Prometheus private-bind correction, with the successful corrective replay recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-monitoring-r7.txt`.
- `make converge-ntfy` completed successfully and is recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-ntfy-r1.txt`.
- The first two `make converge-windmill` replays exposed live drift rather than ADR 0305 model gaps: an unexpected `pgaudit` extension in the Windmill database and an OpenBao partial-unseal helper path that retried the whole keyset even after the service was already unsealed. The manual pgaudit cleanup and unseal evidence are committed under `receipts/live-applies/evidence/2026-03-31-ws-0305-windmill-pgaudit-drop-r1.txt` plus `receipts/live-applies/evidence/2026-03-31-ws-0305-openbao-unseal-r1.txt`/`r2.txt`, and the branch now carries the repo fix that stops replaying unnecessary OpenBao unseal attempts.
- With the OpenBao helper fix in place, `make converge-windmill` completed successfully on replay `r4`, and the live Windmill API now shows `f/lv3/k6_load_testing`, `f/lv3/k6_load_weekly`, and `f/lv3/k6_soak_monthly`; see `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-windmill-r4.txt` and `receipts/live-applies/evidence/2026-03-31-ws-0305-windmill-api-r1.txt`.
- `make converge-openfga` completed successfully on replay `r5`, after the earlier apt-lock drift on `docker-runtime-lv3` cleared; the successful replay is preserved in `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-openfga-r5.txt`.
- `make check-build-server` now prunes stale remote session workspaces via the branch-local retention policy, recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-check-build-server-r2.txt` and `r3.txt`. The live build host still required one operator cleanup of unused Docker images and build cache to recover from full-disk drift; that manual intervention is recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-build-server-docker-prune-r1.txt`.
- The authoritative smoke replay passed from `docker-build-lv3`, producing synced receipts `receipts/k6/smoke-keycloak-20260331T103411Z.json` and `receipts/k6/smoke-openfga-20260331T103411Z.json` with real metrics (`120` requests and `0` failures for each service), as captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-smoke-r9.txt` and `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-receipt-sync-r2.txt`.
- The authoritative load replay now returns the real non-zero threshold failure while still emitting synced receipts and the raw summary export, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-load-r6.txt` and `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-receipt-sync-r3.txt`. Keycloak recorded `1725` requests with `400` failures (`23.19%` error rate) and OpenFGA recorded `995` requests with `42` failures (`4.22%` error rate); both receipts show `error_budget_remaining_pct: 0.0`.
- The final load replay also proved two live operational findings that are now recorded, not hidden: Prometheus remote-write from the build host to `monitoring-lv3` timed out repeatedly (`receipts/live-applies/evidence/2026-03-31-ws-0305-prometheus-build-server-r1.txt`), and the build host does not currently have `ntfy_alertmanager_password`, so warning delivery is unavailable there. The branch now treats those notification failures as receipt warnings rather than aborting receipt generation.

## Merge Criteria

- `make converge-monitoring` and `make converge-windmill` succeed from this worktree, and any required ntfy/runtime follow-up is documented in the live-apply receipt.
- Real `make k6-smoke` and `make k6-load` runs are replayed against the live platform with synced receipts committed under `receipts/k6/`; smoke must pass, and load must either pass or preserve a truthful non-zero threshold-failure receipt when the live platform breaches the declared SLO budget.
- The mainline integration replay updates ADR metadata, release/canonical-truth surfaces, and the final live-apply receipt before `origin/main` is pushed.

## Notes For The Next Assistant

- The private Gitea smoke gate needs `LV3_DOCKER_WORKSPACE_PATH`; the runner fix is branch-local here and should be kept when replaying the exact-main integration.
- The public GitHub validation workflow intentionally stays unchanged because it cannot reach the private OpenFGA and Prometheus endpoints required by the smoke gate.
- The first `make converge-monitoring` replay exposed an unrelated shared-contract bug in `playbooks/services/guest-log-shipping.yml`: the lane map did not cover the `artifact-cache` guest role, so the replay failed late on `artifact-cache-lv3` after the ADR 0305 monitoring surfaces had already converged. This branch carries the corrective lane-map patch and reruns the monitoring replay with fresh evidence.
- The corrective replay succeeded end to end, including the guest-log-shipping stage that previously failed on `artifact-cache-lv3`.
- The live Windmill replay also exposed a repo bug in the OpenBao helper path: the old helper tried to submit the full unseal key list each time, which causes a 500 once the service is already unsealed. This branch splits the helper into per-key includes so the role stops as soon as the API reports `sealed: false`.
- The live smoke replay exposed a repo bug in `scripts/k6_load_testing.py`: Docker wrote the summary export as the container user, which is not always permitted in the remote build workspace. This branch now runs the container as the local workspace UID:GID so `receipts/k6/**` stays writable on `docker-build-lv3`.
- The branch is now live-applied and ready for exact-main integration. The remaining work before `origin/main` moves is to refresh from the latest mainline, rerun the final repo gates plus the authoritative exact-main smoke/load replay from committed source, update the protected integration surfaces on `main`, and publish the canonical mainline receipt.
