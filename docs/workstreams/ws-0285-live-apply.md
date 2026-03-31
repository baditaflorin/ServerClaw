# Workstream ws-0285-live-apply: Live Apply ADR 0285 From Latest `origin/main`

- ADR: [ADR 0285](../adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md)
- Title: Deploy Paperless-ngx as the repo-managed document archive API on `docker-runtime-lv3`
- Status: live_applied
- Included In Repo Version: 0.177.121
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0285-paperless-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0285-paperless-live-apply.json`
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0285-main-integration-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0285-main-integration-r2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0086-backup-and-recovery-for-stateful-services`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0285`, `docs/adr/.index.yaml`, `docs/workstreams/ws-0285-live-apply.md`, `docs/runbooks/configure-paperless.md`, `docs/runbooks/restic-config-backups.md`, `docs/release-notes/`, `docs/diagrams/*.excalidraw`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/paperless.yml`, `playbooks/services/paperless.yml`, `roles/paperless_postgres/`, `roles/paperless_runtime/`, `collections/ansible_collections/lv3/platform/roles/common/tasks/*.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/**`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/**`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/**`, `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/**`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/**`, `collections/ansible_collections/lv3/platform/roles/restic_config_backup/**`, `config/*catalog*.json`, `config/prometheus/**`, `config/grafana/dashboards/`, `config/alertmanager/rules/`, `scripts/generate_platform_vars.py`, `scripts/paperless_sync.py`, `scripts/restic_config_backup.py`, `scripts/trigger_restic_live_apply.py`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `build/platform-manifest.json`, `versions/stack.yaml`, `tests/`, `receipts/image-scans/`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- deploy Paperless-ngx on `docker-runtime-lv3` with repo-managed PostgreSQL,
  Redis, OpenBao-backed runtime secrets, and a backup-covered media volume
- publish the service through the shared NGINX edge at `paperless.lv3.org`
  while preserving the existing `docs.lv3.org` developer portal
- delegate human sign-in to Keycloak OIDC, keep a local break-glass admin for
  bootstrap and recovery, and store the durable API token under repo-managed
  secret paths
- declare the Paperless taxonomy in the role defaults, reconcile it through
  the Paperless API, and verify upload plus search end to end
- leave merge-safe branch-local evidence and note any remaining protected
  `main` integration writes explicitly

## Non-Goals

- replacing the existing `docs.lv3.org` docs portal
- making Paperless a public anonymous surface
- updating protected release surfaces on this branch before the final
  merge-to-`main` step

## Expected Repo Surfaces

- `docs/adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md`
- `docs/runbooks/configure-paperless.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/paperless.yml`
- `playbooks/services/paperless.yml`
- `roles/paperless_postgres/`
- `roles/paperless_runtime/`
- `roles/keycloak_runtime/`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/api-gateway-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/certificate-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/grafana/dashboards/paperless.json`
- `config/grafana/dashboards/slo-overview.json`
- `config/alertmanager/rules/paperless.yml`
- `scripts/generate_platform_vars.py`
- `scripts/paperless_sync.py`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `tests/`
- `workstreams.yaml`

## Expected Live Surfaces

- a healthy Paperless runtime on `docker-runtime-lv3`
- public hostname `paperless.lv3.org`
- authenticated document API at `https://paperless.lv3.org/api/`
- reconciled correspondents, document types, and tags declared from repo state
- a verified upload and search path using the durable API token

## Ownership Notes

- this workstream owns the Paperless runtime, taxonomy sync path, and
  branch-local live-apply evidence
- `docker-runtime-lv3`, `nginx-lv3`, `postgres-lv3`, and `keycloak` are shared
  live surfaces, so replay must stay narrow and preserve unrelated state
- protected integration files remain deferred on this branch until the final
  exact-main replay and merge step

## Branch-Local Delivery

- `779a8cab0` carried the workstream automation onto the active latest-main
  baseline by hardening Paperless, Keycloak, mail-platform, OpenBao, and
  Hetzner DNS recovery paths and by fixing the Paperless smoke-upload verifier
  so each synthetic PDF now contains unique content instead of only unique
  metadata.
- The live replay exposed a transient shared-edge drift where
  `paperless.lv3.org` briefly served the `nginx.lv3.org` certificate; a narrow
  `nginx-lv3,localhost` replay restored the correct `paperless.lv3.org` server
  block and certificate without disturbing unrelated edge publications.
- The same replay surfaced a real verifier defect: deleted smoke documents stay
  in Paperless trash, and the old constant PDF bytes made later probes fail as
  duplicates. The branch tip now embeds the archive serial into the generated
  PDF so repeated public smoke uploads remain valid.

## Verification

- The focused regression slice preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-targeted-pytest-r1.txt`
  passed with `76 passed in 7.06s`, and the post-fix `uv run --with pytest
  pytest tests/test_paperless_sync.py` rerun passed with `7 passed in 0.07s`.
- Repository validation preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-validate-service-completeness-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0285-validate-repo-r2.txt`, and
  `receipts/live-applies/evidence/2026-03-31-ws-0285-git-diff-check-r1.txt`
  confirmed the service catalog, repo automation gate, and whitespace checks
  all passed on the settled branch-local tree.
- Guest-local runtime verification preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-guest-runtime-r3.txt`
  confirmed `paperless`, `paperless-openbao-agent`, and `paperless-redis` all
  stayed healthy on `docker-runtime-lv3`, and the authenticated local API
  returned a clean documents listing.
- Public endpoint verification preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-public-head-r2.txt` and
  `receipts/live-applies/evidence/2026-03-31-ws-0285-public-verify-r3.txt`
  confirmed the correct `paperless.lv3.org` TLS publication and a no-drift
  taxonomy verification result through `https://paperless.lv3.org/api/`.
- Public smoke-upload verification preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-public-smoke-r3.txt` and
  `receipts/live-applies/evidence/2026-03-31-ws-0285-task-log-r1.json`
  confirmed a fresh uploaded document completed ingestion successfully and was
  cleaned back out of the archive.

## Latest Mainline Integration State

- The current integration branch is rebased onto latest `origin/main` commit
  `97f0580225d0eca79104ee35c702f2cef44a819c`, which already includes the
  ADR 0306 `0.177.119` validation-gate cut.
- The merge candidate also carries the post-branch Paperless recovery work:
  `scripts/trigger_restic_live_apply.py` now self-heals the remote runtime
  support bundle before invoking the restic wrapper, and
  `scripts/restic_config_backup.py` writes a live-apply-scoped latest snapshot
  receipt instead of reusing the repo-wide summary.
- The shared Docker runtime recovery path is hardened on this branch: the
  tracked `docker_runtime` role now waits for the local OpenBao listener before
  restarting compose groups that include `openbao-agent`, which prevented the
  One API and Outline recovery loops from racing their own secret sidecars.
- Exact-mainline Paperless prerequisites were re-established on `0.177.119`:
  Outline was recovered through the repo-managed scoped service playbook in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-mainline-outline-recovery-r1-0.177.118.txt`,
  and the authoritative restic trigger then passed in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-mainline-restic-trigger-r11-0.177.118.txt`.
- The authoritative wrapper is governed by ADR 0191 on `docker-runtime-lv3`.
  `make immutable-guest-replacement-plan service=paperless` confirmed that the
  final replay must use the documented narrow exception:
  `ALLOW_IN_PLACE_MUTATION=true HETZNER_DNS_API_TOKEN=... make live-apply-service service=paperless env=production`.
- The first exact-main wrapper replay with the ADR 0191 exception is preserved
  in `receipts/live-applies/evidence/2026-03-31-ws-0285-mainline-live-apply-r9-0.177.118.txt`.
  It converged most of the runtime but failed during the authenticated taxonomy
  wait after an unrelated concurrent Docker restart on `docker-runtime-lv3`.
- Guest logs and journal evidence show the failure was environmental, not a
  Paperless config regression: `paperless` and `paperless-redis` both exited
  cleanly after broker disconnects, and the Docker journal recorded another
  Ansible-driven `docker.service` restart while Paperless verification was
  already in progress.
- As of `2026-03-31T16:52:32Z`, other agents are still actively running
  `playbooks/windmill.yml` and `playbooks/monitoring-stack.yml` against
  `docker-runtime-lv3`, so the final exact-main replay is waiting for a quiet
  window to avoid another false-negative verification failure.

## Mainline Completion

- The authoritative exact-main replay from release `0.177.121` completed
  cleanly on `2026-03-31` from the latest realistic `origin/main` baseline
  `0.177.120 / 0.130.77`, and the full wrapper preserved successful Paperless
  runtime recovery, taxonomy reconciliation, public publication, public smoke
  upload verification, API gateway bundle sync, and shared NGINX edge checks in
  `receipts/live-applies/evidence/2026-03-31-ws-0285-mainline-final-live-apply-r1-0.177.121.txt`.
- The post-apply restic trigger succeeded immediately after the replay and
  recorded snapshot `0ea3c5176e2e123d8e56cc9e6b398e8a49d190d8e25f0c2587838850a7b3692c`
  for `config/` plus snapshot
  `64fa6fc807fb63c6c057c82e67a4abe7ca803b2662ab6548f75a3bb2983340f5` for
  `versions/stack.yaml`.
- ADR 0285 first became true on platform version `0.130.75`; this exact-main
  closeout keeps that first-live milestone intact while advancing the integrated
  platform truth to `0.130.78` alongside repository version `0.177.121`.
- Protected release surfaces and canonical metadata were refreshed on the same
  exact candidate so `main` can fast-forward without any additional Paperless
  integration-only follow-up.
