# Workstream ws-0282-main-merge

- ADR: [ADR 0282](../adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- Title: Integrate ADR 0282 Mailpit exact-main replay onto `origin/main`
- Status: ready_for_merge
- Included In Repo Version: 0.177.96
- Platform Version Observed During Integration: 0.130.63
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0282-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0282-main-merge`
- Owner: codex
- Depends On: `ws-0282-live-apply`

## Purpose

Carry the verified ADR 0282 Mailpit live-apply branch onto the newest
available `origin/main`, rerun the exact-main Mailpit replay from committed
source on that synchronized baseline, cut the protected release and
canonical-truth surfaces from the resulting tree, and publish the Mailpit
rollout on `main` without inventing a new platform-version bump after Mailpit
was already live on `0.130.60`.

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
- `scripts/serverclaw_authz.py`
- `tests/test_serverclaw_authz.py`
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

## Verification

- `git fetch origin --prune` and merge commit
  `41653f0bfd2ec29a60796f50ddbf07dce76a6d87` refreshed this workstream onto the
  latest shared `origin/main`, carrying the integrated ADR 0261 and ADR 0262
  browser-runner and OpenFGA surfaces onto repository version `0.177.95` and
  platform version `0.130.63` before the Mailpit replay.
- Refreshing onto that newer mainline required one more shared-surface repair:
  `Makefile` now carries `browser-runner`, `mailpit`, and `openfga` entrypoints
  together, `config/ansible-role-idempotency.yml` now tracks the merged
  `browser_runner_runtime` role, and the generated manifest, SLO dashboard,
  diagrams, dependency graph, and stack evidence were regenerated from the
  merged source-of-truth files.
- The focused exact-main compatibility slice passed on the merged tree with
  `49 passed in 1.71s` across Mailpit, Keycloak, ServerClaw, and browser-runner
  tests, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-targeted-checks-r8.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production`
  succeeded from committed source `41653f0bfd2ec29a60796f50ddbf07dce76a6d87`
  with final recap
  `docker-runtime-lv3 : ok=115 changed=4 unreachable=0 failed=0 skipped=18 rescued=0 ignored=0`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-live-apply-r7.txt`.
- A fresh guest-local Mailpit probe returned `Version=v1.29.5`, `Messages=1`,
  and `SMTPAccepted=16`, and a fresh probe from `monitoring-lv3` sent SMTP to
  `10.10.10.20:1025` and confirmed exactly one captured message with subject
  `LV3 Mailpit exact-main verification` created at `2026-03-30T04:37:04.036Z`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-mailpit-info-r4.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-monitoring-probe-r4.txt`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py status --json`
  reported the merged release baseline, the matching dry run planned release
  `0.177.96`, and the write run prepared release `0.177.96` while preserving
  `platform_version: 0.130.63`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-release-status-r3.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-release-dry-run-r6.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-release-write-r4.txt`.
- Final automation checks passed on the release tree while the workstream stays
  `ready_for_merge`: `make validate`, `make remote-validate`,
  `make pre-push-gate`, `make check-build-server`, `git diff --check`, and
  `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`
  passed, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-validate-r10.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-remote-validate-r5.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-pre-push-gate-r3.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-check-build-server-r3.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-git-diff-check-r2.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-live-apply-receipts-validate-r2.txt`.
- A fresh current-server state check after the exact-main replay confirmed the
  Proxmox host still reports `Debian-trixie-latest-amd64-base` and
  `pve-manager/9.1.6/71482d1833ded40a (running kernel: 6.17.13-2-pve)`, while
  `docker-runtime-lv3` still runs `mailpit` as a healthy container on image
  digest `sha256:0d7b9c8ed469f400087d9abf1df5b7c7c88b33ae7b8b381ea5a2b153ef27aacf`
  with Mailpit API info `Version=v1.29.5`, `Messages=1`, and
  `SMTPAccepted=18`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-host-state-r1.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-mailpit-runtime-state-r2.txt`.
- A fresh `monitoring-lv3` SMTP probe deleted old Mailpit messages, sent mail
  to `10.10.10.20:1025`, and confirmed exactly one captured message with
  subject `LV3 Mailpit exact-main verification` created at
  `2026-03-30T07:25:12.36Z`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-monitoring-probe-r5.txt`.
- An exploratory live `playbooks/mail-platform-verify.yml -e env=staging` run
  still targeted `docker-runtime-staging-lv3` and failed with `Connection
  refused` on `127.0.0.1:8025` because the current server does not deploy the
  separate staging guest topology; that environment-scope limitation is
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0282-mainline-mail-platform-verify-r1.txt`,
  while the authoritative current-server Mailpit proof remains the direct
  `monitoring-lv3 -> docker-runtime-lv3` probe above.
- The branch intentionally remains `status: ready_for_merge` until the final
  canonical-truth closeout commit is written; that keeps `workstream-surfaces`
  valid on the branch. The final `status: merged` flip and README truth refresh
  are the only remaining integration-only surfaces before pushing to `main`.

## Outcome

- Release `0.177.96` is prepared from the latest merged mainline replay of ADR
  0282.
- Platform version remains `0.130.63` because Mailpit first became true on
  `0.130.60`; release `0.177.96` integrates that already-live capability onto
  the synchronized repo truth instead of advancing the platform baseline again.
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-mainline-live-apply.json`
  is the canonical exact-main proof for Mailpit from committed source
  `41653f0bfd2ec29a60796f50ddbf07dce76a6d87`, superseding the earlier
  branch-local receipt while preserving it in the audit trail.
