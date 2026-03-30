# Workstream ws-0282-main-merge

- ADR: [ADR 0282](../adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- Title: Integrate ADR 0282 Mailpit live apply into `origin/main`
- Status: ready_for_merge
- Included In Repo Version: not yet
- Platform Version Observed During Merge: 0.130.60
- Release Date: not yet
- Branch: `codex/ws-0282-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0282-main-merge`
- Owner: codex
- Depends On: `ws-0282-live-apply`

## Purpose

Carry the verified ADR 0282 Mailpit live-apply branch onto the latest
`origin/main`, cut the protected release and canonical-truth surfaces from that
merged baseline, rerun the integrated validation bundle, and publish the
Mailpit rollout on `main` without inventing a second live event when the
latest-main replay has already been verified on platform version `0.130.60`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0282-main-merge.md`
- `docs/workstreams/ws-0282-live-apply.md`
- `docs/adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-mailpit.md`
- `docs/runbooks/configure-mail-platform.md`
- `inventory/group_vars/all.yml`
- `inventory/group_vars/staging.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `collections/ansible_collections/lv3/platform/playbooks/mailpit.yml`
- `collections/ansible_collections/lv3/platform/roles/mailpit_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `playbooks/mailpit.yml`
- `playbooks/services/mailpit.yml`
- `playbooks/mail-platform-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml`
- `config/ansible-execution-scopes.yaml`
- `config/command-catalog.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/slo-catalog.json`
- `config/workflow-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `Makefile`
- `scripts/generate_platform_vars.py`
- `scripts/validate_repo.sh`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_mailpit_playbook.py`
- `tests/test_mailpit_runtime_role.py`
- `tests/test_mail_platform_verify_playbook.py`
- `config/ansible-role-idempotency.yml`
- `scripts/remote_exec.sh`
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
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-live-apply.json`

## Plan

- carry the finished Mailpit live-apply branch onto the latest `origin/main`
- cut the next patch release from that merged candidate
- refresh canonical truth so `versions/stack.yaml` records the Mailpit receipt
  while keeping `platform_version` at `0.130.60`, because the rebased latest-main
  live replay already proved the platform change before this release cut
- rerun the integrated validation and release automation paths before pushing
  `origin/main`

## Verification

- `git fetch origin --prune` refreshed this integration worktree from the latest published `origin/main`
- `git merge --ff-only codex/ws-0282-live-apply` carried the finished Mailpit branch onto the exact-main integration worktree without reopening branch-local conflicts
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-live-apply.json` remains the canonical live proof for the rebased latest-main replay and the independent SMTP capture from `monitoring-lv3`

## Current State

- The ADR 0282 Mailpit implementation and live verification are complete on the carried workstream branch.
- This integration branch now owns the protected release surfaces needed to publish that already-verified Mailpit rollout on `main`.
- The remaining work is the release cut, canonical-truth refresh, integration-side validation pass, and final push to `origin/main`.
