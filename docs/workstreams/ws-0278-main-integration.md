# Workstream ws-0278-main-integration

- ADR: [ADR 0278](../adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md)
- Title: Integrate ADR 0278 exact-main replay onto `origin/main`
- Status: `live_applied`
- Target Repo Version: `0.177.92`
- Platform Version Before Exact-Main Replay: `0.130.60`
- Live Applied In Platform Version: `0.130.61`
- Branch: `codex/ws-0278-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0278-main-integration`
- Owner: codex
- Depends On: `ws-0278-live-apply`

## Purpose

Carry the verified ADR 0278 Gotenberg rollout from the branch-local latest-main
proof onto the newest `origin/main`, refresh the protected release and
canonical-truth surfaces from that merged baseline, replay the Gotenberg
service from merged `main`, and then record the canonical mainline receipt plus
platform-version bump.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0278-main-integration.md`
- `docs/workstreams/ws-0278-live-apply.md`
- `docs/adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md`
- `docs/adr/.index.yaml`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/runbooks/configure-gotenberg.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `config/grafana/dashboards/gotenberg.json`
- `config/alertmanager/rules/gotenberg.yml`
- `playbooks/gotenberg.yml`
- `playbooks/services/gotenberg.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/gotenberg_runtime/**`
- `tests/test_docker_runtime_role.py`
- `tests/test_gotenberg_runtime_role.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/diagrams/trust-tier-model.excalidraw`
- `receipts/image-scans/2026-03-30-gotenberg-runtime.json`
- `receipts/image-scans/2026-03-30-gotenberg-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0278-gotenberg-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0278-gotenberg-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0278-*`

## Verification So Far

- the branch-local latest-main proof for ADR 0278 completed successfully and is
  preserved in `receipts/live-applies/2026-03-30-adr-0278-gotenberg-live-apply.json`
- the first merged-main replay from commit `8704a9798` failed in
  `receipts/live-applies/evidence/2026-03-30-ws-0278-merged-main-live-apply.txt`
  because reloading the full nftables ruleset flushed Docker-managed tables and
  left Gotenberg without a usable `DOCKER` nat chain during startup
- commit `e1b0ceb64` patched the Docker runtime role so the forward-compat
  rules are applied live without reloading the full nftables ruleset, and the
  focused Docker runtime plus Gotenberg pytest slice covers that behavior
- the authoritative merged-main replay from commit `e1b0ceb64` succeeded with
  recap `docker-runtime-lv3 : ok=259 changed=112 unreachable=0 failed=0 skipped=29 rescued=0 ignored=0`, captured in
  `receipts/live-applies/evidence/2026-03-30-ws-0278-merged-main-live-apply-r2.txt`
- fresh merged-main checks succeeded for guest-local health, guest-local
  Chromium and LibreOffice conversion, authenticated gateway health, and
  authenticated gateway Chromium conversion, with evidence in the
  `2026-03-30-ws-0278-merged-main-*` files
- the local validation slice passed: focused pytest, syntax check,
  ansible-scope validation, repository data-model validation, live-apply
  receipt validation, canonical truth, platform manifest, generated docs, and
  `git diff --check`
- `git push origin HEAD:main` ran the full remote pre-push gate successfully
  for both the initial `0.177.92` release integration and the follow-up Docker
  runtime replay fix, with all documented validation lanes passing each time

## Current State

- release `0.177.92` and the Docker runtime replay fix commit `e1b0ceb64` are
  already on `origin/main`
- the authoritative merged-main replay and fresh local plus gateway proofs are
  complete, and this worktree now carries the canonical receipt plus
  `platform_version` bump for the resulting mainline state
- no service-health or repository-validation blocker remains for ADR 0278

## Remaining For Merge-To-Main

- none; this document remains as the integration audit trail for the merged
  `origin/main` replay and the Docker runtime recovery fix that made it
  reliable
