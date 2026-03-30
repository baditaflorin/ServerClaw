# Workstream ws-0291-main-merge

- ADR: [ADR 0291](../adr/0291-jupyterhub-as-the-interactive-notebook-environment.md)
- Title: Integrate ADR 0291 JupyterHub exact-main replay onto `origin/main`
- Status: in_progress
- Included In Repo Version: pending
- Platform Version Observed During Integration: pending
- Release Date: pending
- Live Applied On: pending
- Branch: `codex/ws-0291-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0291-main-merge`
- Owner: codex
- Depends On: `ws-0291-live-apply`

## Purpose

Carry the verified ADR 0291 JupyterHub live-apply branch onto the newest
available `origin/main`, rerun the exact-main notebook replay from committed
source on that synchronized baseline, cut the protected release and
canonical-truth surfaces from the resulting tree, and publish the JupyterHub
notebook environment on `main` with current live evidence instead of relying on
branch-local state alone.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0291-main-merge.md`
- `docs/workstreams/ws-0291-live-apply.md`
- `docs/adr/0291-jupyterhub-as-the-interactive-notebook-environment.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-jupyterhub.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `scripts/validate_repo.sh`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/api-gateway-catalog.json`
- `config/certificate-catalog.json`
- `config/service-completeness.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-redundancy-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `playbooks/jupyterhub.yml`
- `playbooks/services/jupyterhub.yml`
- `collections/ansible_collections/lv3/platform/roles/jupyterhub_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/ollama_runtime/`
- `tests/test_generate_platform_vars.py`
- `tests/test_jupyterhub_runtime_role.py`
- `tests/test_jupyterhub_playbook.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_ollama_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_edge_publication_makefile.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0291-*`

## Verification

- pending

## Outcome

- pending
