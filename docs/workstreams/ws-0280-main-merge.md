# Workstream ws-0280-main-merge

- ADR: [ADR 0280](../adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- Title: Integrate ADR 0280 Changedetection exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.100
- Platform Version Observed During Integration: 0.130.66
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0280-main-merge-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0280-main-merge`
- Owner: codex
- Depends On: `ws-0280-live-apply`

## Purpose

Carry the verified ADR 0280 Changedetection workstream onto the newest
available `origin/main`, rerun the exact-main replay from committed source on
that synchronized baseline, refresh the protected release and canonical-truth
surfaces from the resulting tree, and publish the private Changedetection
runtime plus its authenticated `/v1/changedetection` gateway contract on
`main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0280-main-merge.md`
- `docs/workstreams/ws-0280-live-apply.md`
- `docs/adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-changedetection.md`
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
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/diagrams/trust-tier-model.excalidraw`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.j2`
- `collections/ansible_collections/lv3/platform/roles/mattermost_runtime/templates/mattermost.env.ctmpl.j2`
- `collections/ansible_collections/lv3/platform/roles/netbox_runtime/defaults/main.yml`
- `playbooks/changedetection.yml`
- `playbooks/services/changedetection.yml`
- `collections/ansible_collections/lv3/platform/roles/changedetection_runtime/`
- `scripts/changedetection_sync.py`
- `tests/test_changedetection_runtime_role.py`
- `tests/test_changedetection_metadata.py`
- `tests/test_changedetection_sync.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_data_retention_role.py`
- `tests/test_openbao_runtime_role.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.json`
- `receipts/image-scans/2026-03-30-changedetection-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-*`

## Verification

- `git fetch origin --prune` confirmed the latest shared `origin/main` baseline
  is commit `ba70f6936291dfa44f42e1ff694b1d6cb6cd0d4f`, which already carries the
  ADR 0283 integration release `0.177.99` and platform version `0.130.66`.
- ADR 0280 was replayed onto that newer baseline by cherry-picking the four
  functional Changedetection commits onto `codex/ws-0280-main-merge-r2`; the
  one generated-file conflict in
  `config/grafana/dashboards/slo-overview.json` was resolved by preserving the
  newer mainline source-of-truth inputs and regenerating the dashboard from the
  merged catalog state.
- The focused exact-main compatibility slice passed with `64 passed in 2.57s`
  across the Changedetection, platform-vars, Mattermost, NetBox, OpenBao,
  data-retention, and Plausible regressions, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-targeted-checks-r1.txt`.
- The syntax sweep passed for the Changedetection, Plausible, Mattermost, and
  NetBox lanes, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-syntax-checks-r1.txt`.
- The exact-main release manager dry run confirmed the merged baseline at
  `0.177.99` and the next release at `0.177.100`, and the write run prepared
  release `0.177.100` while preserving the pre-replay platform baseline at
  `0.130.66`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-release-dry-run-r1.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r2-release-write-r1.txt`.
- The authoritative exact-main replay from committed source
  `65305c70c7049bcb177f59b5a44ab0d031a8a10c` succeeded in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-live-apply-0.177.100.txt`
  with final recap
  `docker-runtime-lv3 : ok=312 changed=115 unreachable=0 failed=0 skipped=32 rescued=0 ignored=0`.
- Fresh post-commit proofs from that replay confirmed the current server still
  reports `Debian-trixie-latest-amd64-base`,
  `pve-manager/9.1.6/71482d1833ded40a (running kernel: 6.17.13-2-pve)`, and
  `sudo qm status 120 => status: running`, while `docker-runtime-lv3` serves a
  healthy Changedetection `0.54.7` runtime with `watch_count == 9`,
  `tag_count == 4`, and a drift-free sync report, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-host-state-r1-0.177.100.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-changedetection-runtime-state-r1-0.177.100.txt`.
- A fresh authenticated controller-side probe of
  `https://api.lv3.org/v1/changedetection/` returned the live Changedetection
  UI HTML for version `0.54.7`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-gateway-route-r1-0.177.100.html`.
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`
  records the canonical exact-main receipt from committed source
  `65305c70c7049bcb177f59b5a44ab0d031a8a10c`, while the earlier branch-local
  receipt remains preserved as first-live audit history on platform version
  `0.130.63`.
- Final branch-side automation checks all passed while this workstream remains
  `ready_for_merge`: `git diff --check`,
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`,
  `make remote-validate`, and `make pre-push-gate`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-git-diff-check-r1-0.177.100.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-live-apply-receipts-validate-r1-0.177.100.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-data-model-validate-r1-0.177.100.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-branch-validate-r1-0.177.100.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-remote-validate-r1-0.177.100.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-r3-pre-push-gate-r1-0.177.100.txt`.
- The terminal main-candidate closeout flips this workstream to
  `status: merged`; after that closeout, `git diff --check`,
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  and `make pre-push-gate` are rerun on the detached main candidate, preserved
  in
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-main-candidate-git-diff-check-r1.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-main-candidate-live-apply-receipts-validate-r1.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0280-mainline-main-candidate-pre-push-gate-r1.txt`.

## Outcome

- Release `0.177.100` now carries ADR 0280 onto the latest shared mainline
  baseline of `0.177.99 / 0.130.66`.
- The authoritative committed replay from
  `65305c70c7049bcb177f59b5a44ab0d031a8a10c` refreshed the private
  Changedetection runtime and authenticated `/v1/changedetection` gateway route
  on the live server, and the integrated canonical truth advances the tracked
  platform baseline to `0.130.67`.
- `receipts/live-applies/2026-03-30-adr-0280-changedetection-mainline-live-apply.json`
  is the canonical mainline receipt for ADR 0280; the earlier branch-local
  receipt on `0.130.63` remains part of the audit trail.
