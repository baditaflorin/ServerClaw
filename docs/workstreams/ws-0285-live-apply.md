# Workstream ws-0285-live-apply: Live Apply ADR 0285 From Latest `origin/main`

- ADR: [ADR 0285](../adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md)
- Title: Deploy Paperless-ngx as the repo-managed document archive API on `docker-runtime-lv3`
- Status: live_applied
- Included In Repo Version: N/A
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0285-paperless-live-apply.json`
- Canonical Mainline Receipt: pending
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0285-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0285-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0086-backup-and-recovery-for-stateful-services`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0285`, `docs/workstreams/ws-0285-live-apply.md`, `docs/runbooks/configure-paperless.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/paperless.yml`, `playbooks/services/paperless.yml`, `roles/paperless_postgres/`, `roles/paperless_runtime/`, `roles/keycloak_runtime/`, `config/*catalog*.json`, `config/prometheus/**`, `config/grafana/dashboards/`, `config/alertmanager/rules/`, `scripts/generate_platform_vars.py`, `scripts/paperless_sync.py`, `tests/`, `receipts/image-scans/`, `receipts/live-applies/`, `workstreams.yaml`

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

## Remaining For Merge-To-Main

- rebase or merge this workstream onto the current `origin/main` head
  `ad0050483c76e6eba2f516cbb6d4e4f4a6843476`
- cut the protected main integration surfaces with the next repo release bump
  and canonical-truth refresh
- replay the exact merged `main` tree through the authoritative
  `make live-apply-service service=paperless env=production` path
- record the canonical mainline receipt and bump `versions/stack.yaml` to the
  first exact-main platform version only after that replay passes
