# Workstream ws-0283-live-apply: Live Apply ADR 0283 From Latest `origin/main`

- ADR: [ADR 0283](../adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md)
- Title: Deploy Plausible Analytics on `docker-runtime-lv3`, publish it at `analytics.lv3.org`, and verify privacy-first page tracking end to end
- Status: in_progress
- Implemented In Repo Version: pending main integration
- Live Applied In Platform Version: pending exact-main replay
- Implemented On: pending
- Live Applied On: pending
- Branch: `codex/ws-0283-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0283-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0077-compose-secret-injection`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0283`, `docs/workstreams/ws-0283-live-apply.md`, `docs/runbooks/configure-plausible.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/plausible.yml`, `playbooks/services/plausible.yml`, `roles/plausible_runtime/`, `roles/nginx_edge_publication/`, `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `receipts/image-scans/`, `receipts/live-applies/`, `tests/`

## Scope

- deploy Plausible Community Edition on `docker-runtime-lv3` with repo-managed PostgreSQL, ClickHouse, and OpenBao-backed runtime secrets
- publish `analytics.lv3.org` through the shared NGINX edge with dashboard access gated by the existing edge OIDC flow while tracker and health endpoints remain public
- register a conservative set of public, non-authenticated LV3 pages as Plausible sites and inject the tracker through the shared edge publication template
- verify runtime health, bootstrap state, tracker injection, and one accepted synthetic analytics event before recording the live-apply receipt

## Non-Goals

- introducing service-native Plausible Enterprise features that are absent from Community Edition
- tracking authenticated internal operator traffic or API-only traffic
- updating protected release surfaces on this workstream branch before the final `main` integration step

## Expected Repo Surfaces

- `docs/adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md`
- `docs/runbooks/configure-plausible.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/plausible.yml`
- `playbooks/services/plausible.yml`
- `roles/plausible_runtime/`
- `roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/service-completeness.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `tests/`
- `workstreams.yaml`

## Expected Live Surfaces

- Plausible Community Edition stack running on `docker-runtime-lv3`
- public hostname `analytics.lv3.org`
- public tracker script and event endpoints at `https://analytics.lv3.org/js/` and `https://analytics.lv3.org/api/event`
- repo-managed analytics injection on the selected public LV3 pages

## Ownership Notes

- this workstream owns the Plausible runtime, edge injection contract, and the branch-local live-apply evidence
- `docker-runtime-lv3` and `nginx-lv3` are shared live surfaces, so replay must use the governed service wrapper and a documented narrow in-place exception if ADR 0191 blocks the default path
- protected integration files remain deferred on this branch until the exact-main replay and final merge step
