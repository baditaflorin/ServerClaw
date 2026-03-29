# Workstream ws-0260-live-apply: ADR 0260 Live Apply From Latest `origin/main`

- ADR: [ADR 0260](../adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md)
- Title: Nextcloud personal data plane live apply from latest `origin/main`
- Status: in_progress
- Branch: `codex/ws-0260-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0260-live-apply`
- Owner: codex
- Depends On: `adr-0206-ports-and-adapters-for-external-integrations`, `adr-0259-n8n-as-the-external-app-connector-fabric-for-serverclaw`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/restore_verification.py`, `collections/ansible_collections/lv3/platform/playbooks/nextcloud.yml`, `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`, `collections/ansible_collections/lv3/platform/roles/nextcloud_postgres`, `collections/ansible_collections/lv3/platform/roles/nextcloud_runtime`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `config/health-probe-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/dependency-graph.json`, `config/service-redundancy-catalog.json`, `config/data-catalog.json`, `config/slo-catalog.json`, `config/service-completeness.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/capability-contract-catalog.json`, `config/replaceability-review-catalog.json`, `config/grafana/dashboards/nextcloud.json`, `config/grafana/dashboards/slo-overview.json`, `config/alertmanager/rules/nextcloud.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/slo_rules.yml`, `config/uptime-kuma/monitors.json`, `Makefile`, `docs/runbooks/`, `receipts/image-scans/`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- deploy Nextcloud on `docker-runtime-lv3` as the canonical personal data plane for files, WebDAV, CalDAV, and CardDAV
- provision a dedicated PostgreSQL backend on `postgres-lv3`
- publish `cloud.lv3.org` through the shared `nginx-lv3` edge with large-upload and DAV redirect support
- capture repo-managed controller-local bootstrap artifacts and runtime secret injection for the service
- verify public and guest-local health, DAV redirect behavior, background cron mode, and repo automation contracts from the latest synchronized `origin/main`

## Non-Goals

- bumping `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, or the top-level integrated `README.md` before the final merge-to-`main` step
- introducing a second identity provider or replacing app-native Nextcloud login with shared edge OIDC
- redesigning the broader backup policy beyond the already-declared runtime filesystem and PostgreSQL protection model

## Planned Verification

- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `python3 -m pytest -q tests/test_nextcloud_playbook.py tests/test_nextcloud_runtime_role.py tests/test_generate_platform_vars.py tests/test_nginx_edge_publication_role.py tests/test_service_topology_filters.py tests/test_postgres_vm_access_policy.py`
- `make syntax-check-nextcloud`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/container_image_policy.py --validate`
- `python3 scripts/service_completeness.py --service nextcloud`
- `make generate-uptime-kuma-monitors`
- `make converge-nextcloud`
- `curl -fsS https://cloud.lv3.org/status.php`
- `curl -fsSI https://cloud.lv3.org/.well-known/caldav`
- `curl -fsSI https://cloud.lv3.org/.well-known/carddav`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'curl -fsS http://127.0.0.1:8084/status.php'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'docker exec --user www-data nextcloud-app php occ config:app:get core backgroundjobs_mode'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'docker exec --user www-data nextcloud-app php occ user:info ops --output=json'`

## Notes

- The branch-local work can add all ADR-local, workstream-local, and service-local state needed for a safe merge.
- Protected integration files remain deferred until the final exact-main replay and merge step.
