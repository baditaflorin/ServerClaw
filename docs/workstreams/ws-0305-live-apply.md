# Workstream ws-0305-live-apply: Live Apply ADR 0305 From Latest `origin/main`

- ADR: [ADR 0305](../adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- Title: Live apply k6 smoke, load, and soak validation with Prometheus remote-write, Windmill schedules, and promotion-gate burn checks from latest `origin/main`
- Status: in_progress
- Branch: `codex/ws-0305-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0305-live-apply`
- Owner: codex
- Depends On: `adr-0096-slo-tracking`, `adr-0119-budgeted-workflow-scheduler`, `adr-0123-service-uptime-contracts-and-monitor-backed-health`, `adr-0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization`, `adr-0276-nats-jetstream-as-the-platform-event-bus`, `adr-0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer`, `adr-0299-ntfy-as-the-push-notification-channel`, `adr-0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0305-live-apply.md`, `docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md`, `docs/runbooks/k6-load-testing.md`, `docs/schema/k6-receipt.schema.json`, `docs/schema/capacity-model.schema.json`, `Makefile`, `.gitea/workflows/validate.yml`, `config/image-catalog.json`, `config/capacity-model.json`, `config/k6/scripts/http-slo-probe.js`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/control-plane-lanes.json`, `config/api-publication.json`, `config/event-taxonomy.yaml`, `config/ntfy/server.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/k6_load_testing.py`, `scripts/capacity_report.py`, `scripts/promotion_pipeline.py`, `scripts/slo_tracking.py`, `scripts/validate_nats_topics.py`, `scripts/validate_repository_data_models.py`, `platform/slo.py`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/**`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/**`, `config/windmill/scripts/k6-load-testing.py`, `tests/test_k6_load_testing.py`, `tests/test_k6_load_testing_windmill.py`, `tests/test_gitea_workflows.py`, `tests/test_capacity_report.py`, `tests/test_monitoring_vm_role.py`, `tests/test_windmill_default_operations_surface.py`, `tests/test_windmill_operator_admin_app.py`, `tests/test_promotion_pipeline.py`, `tests/test_slo_tracking.py`, `tests/unit/test_event_taxonomy.py`, `receipts/image-scans/2026-03-31-k6-runtime.json`, `receipts/image-scans/2026-03-31-k6-runtime.trivy.json`, `receipts/k6/`, `receipts/live-applies/`

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
- `receipts/image-scans/2026-03-31-k6-runtime.json`
- `receipts/image-scans/2026-03-31-k6-runtime.trivy.json`
- `.gitea/workflows/validate.yml`
- `scripts/k6_load_testing.py`
- `scripts/capacity_report.py`
- `scripts/slo_tracking.py`
- `scripts/promotion_pipeline.py`
- `platform/slo.py`
- `docs/runbooks/k6-load-testing.md`
- `workstreams.yaml`
- `docs/workstreams/ws-0305-live-apply.md`

## Expected Live Surfaces

- `docker-build-lv3` can run the pinned `k6_runtime` smoke gate against Keycloak and OpenFGA while remote-writing into Prometheus on `monitoring-lv3`
- `docker-runtime-lv3` seeds `f/lv3/k6_load_testing`, `f/lv3/k6_load_weekly`, and `f/lv3/k6_soak_monthly` through the Windmill replay
- `monitoring-lv3` listens on the private Prometheus address needed by the build host and Windmill worker

## Ownership Notes

- `workstreams.yaml` and `docs/adr/.index.yaml` remain shared-contract surfaces and must be updated in a merge-safe way.
- The image-scan receipt, the workstream note, and the live-apply evidence files are branch-local exclusive surfaces for this workstream.
- Protected integration surfaces stay out of scope here until the exact-main replay is complete and verified.

## Verification

- Local Trivy scanning of `docker.io/grafana/k6:1.7.1@sha256:44bd1d66c2b019327991b95459d78402b0a7a0a055ab52ee088deea1a044e8d5` returned `critical=0` and `high=1`, recorded in `receipts/image-scans/2026-03-31-k6-runtime.json` with the raw report beside it.
- The branch already carries the focused pytest and contract coverage for the k6 runner, Windmill wrapper, monitoring role, event taxonomy, SLO tracking, and promotion gate surfaces; those checks are rerun before live apply and before merge.
- `make converge-monitoring` now completes successfully from this worktree after the lane-map repair, with the failed first replay preserved in `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-monitoring-r1.txt` and the successful corrective replay recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-monitoring-r2.txt`.
- Remaining work before merge: exact live replay, real smoke/load receipts, final ADR metadata updates, final canonical-truth integration, and the push to `origin/main`.

## Merge Criteria

- `make converge-monitoring` and `make converge-windmill` succeed from this worktree, and any required ntfy/runtime follow-up is documented in the live-apply receipt.
- Real `make k6-smoke` and `make k6-load` runs succeed against the live platform with receipts committed under `receipts/k6/`.
- The mainline integration replay updates ADR metadata, release/canonical-truth surfaces, and the final live-apply receipt before `origin/main` is pushed.

## Notes For The Next Assistant

- The private Gitea smoke gate needs `LV3_DOCKER_WORKSPACE_PATH`; the runner fix is branch-local here and should be kept when replaying the exact-main integration.
- The public GitHub validation workflow intentionally stays unchanged because it cannot reach the private OpenFGA and Prometheus endpoints required by the smoke gate.
- The first `make converge-monitoring` replay exposed an unrelated shared-contract bug in `playbooks/services/guest-log-shipping.yml`: the lane map did not cover the `artifact-cache` guest role, so the replay failed late on `artifact-cache-lv3` after the ADR 0305 monitoring surfaces had already converged. This branch carries the corrective lane-map patch and reruns the monitoring replay with fresh evidence.
- The corrective replay succeeded end to end, including the guest-log-shipping stage that previously failed on `artifact-cache-lv3`.
