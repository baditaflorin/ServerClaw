# Workstream ws-0291-live-apply: Live Apply ADR 0291 From Latest `origin/main`

- ADR: [ADR 0291](../adr/0291-jupyterhub-as-the-interactive-notebook-environment.md)
- Title: Deploy JupyterHub on `docker-runtime-lv3`, publish `notebooks.lv3.org`, and verify the interactive notebook environment end to end
- Status: live_applied
- Included In Repo Version: 0.177.111
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.71
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0291-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0291-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0145-ollama`, `adr-0274-minio-as-the-s3-compatible-object-storage-layer`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0291`, `docs/workstreams/ws-0291-live-apply.md`, `docs/runbooks/configure-jupyterhub.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `playbooks/jupyterhub.yml`, `playbooks/services/jupyterhub.yml`, `roles/jupyterhub_runtime/`, `roles/keycloak_runtime/`, `roles/nginx_edge_publication/`, `config/*catalog*.json`, `config/subdomain-exposure-registry.json`, `config/uptime-kuma/monitors.json`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/slo_rules.yml`, `config/grafana/dashboards/slo-overview.json`, `config/ansible-execution-scopes.yaml`, `Makefile`, `scripts/validate_repo.sh`, `receipts/live-applies/`, `tests/`

## Scope

- deploy JupyterHub on `docker-runtime-lv3` with a repo-built hub image, a repo-built single-user image, and OpenBao-rendered runtime secrets
- publish the browser surface at `https://notebooks.lv3.org` through the shared NGINX edge and verify Keycloak OIDC login handoff
- create the dedicated confidential Keycloak client used by JupyterHub browser sign-in
- expose the exploratory notebook contract inside spawned user servers with Ollama, the private platform-context API, and a service-local shared MinIO bucket
- verify a repo-managed smoke user through the JupyterHub admin API, including server spawn, environment contract checks, and shutdown cleanup

## Non-Goals

- claiming that shared global MinIO, raw Qdrant, or LiteLLM are already live dependencies for notebooks
- updating protected release truth surfaces on this workstream branch before the exact-main integration step
- broadening notebook access beyond the declared public hostname and governed authenticated API path

## Expected Repo Surfaces

- `docs/adr/0291-jupyterhub-as-the-interactive-notebook-environment.md`
- `docs/workstreams/ws-0291-live-apply.md`
- `docs/runbooks/configure-jupyterhub.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `playbooks/jupyterhub.yml`
- `playbooks/services/jupyterhub.yml`
- `roles/jupyterhub_runtime/`
- `roles/keycloak_runtime/`
- `roles/nginx_edge_publication/`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/certificate-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/dependency-graph.json`
- `config/api-gateway-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `Makefile`
- `scripts/validate_repo.sh`
- `receipts/live-applies/`
- `tests/`
- `workstreams.yaml`

## Expected Live Surfaces

- JupyterHub runtime, sidecar MinIO, and OpenBao agent on `docker-runtime-lv3`
- public hostname `notebooks.lv3.org` for browser access and `/hub/health` verification
- authenticated gateway prefix `/v1/jupyterhub` for operator API access
- dedicated Keycloak OIDC client `jupyterhub`
- controller-local generated artifacts under `.local/jupyterhub/`

## Ownership Notes

- this workstream owns the JupyterHub runtime, the branch-local live-apply evidence, and the notebook-environment contract documentation
- `docker-runtime-lv3`, `nginx-lv3`, and the shared Keycloak runtime are cross-service live surfaces, so replay must stay inside the governed service workflow and document any narrow in-place exception
- protected integration files remain deferred on this branch until the exact-main replay and final merge step

## Purpose

Implement ADR 0291 by making JupyterHub the repo-managed interactive notebook
environment on `docker-runtime-lv3`, publishing it at `notebooks.lv3.org`,
verifying the live spawn contract against current platform services, and leaving
a complete audit trail for the later exact-main replay.

## Delivery Notes

- implementation is in progress from the latest `origin/main` baseline in the dedicated `codex/ws-0291-live-apply` worktree
- the branch-local apply will update ADR-local metadata, runbooks, inventories, service catalogs, validation hooks, and live receipts without touching protected release truth until the final integration step

## Verification

- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-live-apply.json`
  captures the branch-local proof from repository baseline `0.177.108` and
  platform baseline `0.130.71`.
- `make converge-jupyterhub env=production` succeeded on replay `r10` with
  final recap `docker-runtime-lv3 : ok=279 changed=5 failed=0 skipped=81`,
  `localhost : ok=24 changed=0 failed=0 skipped=4`, and
  `nginx-lv3 : ok=40 changed=5 failed=0 skipped=6`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-jupyterhub-converge-r10.txt`.
- Direct controller verification confirmed the public health endpoint, the
  Keycloak OIDC redirect at `https://notebooks.lv3.org/hub/oauth_login`, the
  shared edge certificate SAN for `notebooks.lv3.org`, and the local JupyterHub,
  Ollama, and platform-context probes on `docker-runtime-lv3`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-direct-verification.txt`.

## Outcome

- ADR 0291 is live on the current platform from the branch-local replay.
- Release `0.177.111` integrates the notebook environment onto `main`.
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-mainline-live-apply.json`
  supersedes the branch-local receipt as the canonical exact-main proof while
  preserving the earlier branch-local audit trail.
- The current integrated mainline baseline remains `0.130.73` with no
  additional platform-version bump beyond the earlier `0.130.71` live-apply
  milestone for ADR 0291.
