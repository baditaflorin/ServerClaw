# Workstream ws-0285-live-apply: Live Apply ADR 0285 From Latest `origin/main`

- ADR: [ADR 0285](../adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md)
- Title: Deploy Paperless-ngx as the repo-managed document archive API on `docker-runtime-lv3`
- Status: in_progress
- Included In Repo Version: N/A
- Branch-Local Receipt: pending
- Canonical Mainline Receipt: pending
- Live Applied In Platform Version: N/A
- Implemented On: pending
- Live Applied On: pending
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

## Remaining For Merge-To-Main

- branch-local work is still in progress
- protected release surfaces remain intentionally untouched until the exact-main
  integration step
