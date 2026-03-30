# Workstream ws-0278-main-integration

- ADR: [ADR 0278](../adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md)
- Title: Integrate ADR 0278 exact-main replay onto `origin/main`
- Status: `in-progress`
- Target Repo Version: `0.177.92`
- Platform Version Before Exact-Main Replay: `0.130.60`
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
- the first exact-main candidate replay from release `0.177.92` succeeded, an
  external Docker restart on `docker-runtime-lv3` later stopped the runtime,
  and the governed recovery replay re-established the healthy state
- fresh post-recovery checks succeeded for guest-local health, guest-local
  Chromium and LibreOffice conversion, authenticated gateway health, and
  authenticated gateway Chromium conversion, with evidence in the
  `2026-03-30-ws-0278-mainline-*` files
- the local validation slice passed: focused pytest, syntax check,
  ansible-scope validation, repository data-model validation, live-apply
  receipt validation, canonical truth, platform manifest, generated docs, and
  `git diff --check`
- the first `git push origin HEAD:main` attempt ran the full remote pre-push
  gate and every check passed except `workstream-surfaces`, which failed only
  because this integration branch had not yet been registered in
  `workstreams.yaml`
- the first merged-main replay exposed a Docker-runtime recovery bug: reloading
  the full nftables ruleset to persist the forward-compat patch flushed
  Docker-managed tables, restarted the daemon, and left Gotenberg racing a
  transient `iptables -t nat DOCKER` / bridge-network restore window

## Current State

- release `0.177.92` is ready to merge from this branch
- exact-main replay evidence exists, but the authoritative merged-main receipt
  and `platform_version` bump must wait until the push succeeds and the replay
  is repeated from the resulting `main` commit
- the remaining blocker is branch-ownership registration for this integration
  branch, not service health or repo-validation drift

## Remaining For Merge-To-Main

- rerun `git push origin HEAD:main` after this workstream registration lands
- replay `make live-apply-service service=gotenberg env=production` from the
  merged `main` commit and capture the canonical mainline receipt
- update `versions/stack.yaml`, the ADR metadata, the workstream docs, and the
  generated canonical-truth surfaces after the merged-main replay is verified
