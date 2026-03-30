# Workstream ws-0288-live-apply: ADR 0288 Live Apply From Latest `origin/main`

- ADR: [ADR 0288](../adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md)
- Title: deploy Flagsmith as the repo-managed feature flag and remote configuration control plane
- Status: in_progress
- Branch: `codex/ws-0288-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0288-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021`, `adr-0023`, `adr-0042`, `adr-0077`, `adr-0086`
- Conflicts With: none

## Scope

- add the repo-managed Flagsmith runtime, PostgreSQL setup, edge publication, secret mirrors, image pinning, health probes, and workflow metadata
- live-apply the service from an isolated latest-main worktree and verify local and public behaviour end to end
- carry the verified change through exact-main integration once the workstream branch is fully validated

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0288-live-apply.md`
- `docs/adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md`
- `docs/runbooks/configure-flagsmith.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/subdomain-catalog.json`
- `config/certificate-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `playbooks/flagsmith.yml`
- `playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_postgres/`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_runtime/`
- `scripts/flagsmith_seed.py`
- `tests/test_flagsmith_playbook.py`
- `tests/test_flagsmith_runtime_role.py`
- `receipts/image-scans/2026-03-30-flagsmith-runtime.json`
- `receipts/live-applies/`

## Verification Plan

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_flagsmith_runtime_role.py tests/test_flagsmith_playbook.py tests/test_generate_platform_vars.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py`
- `make syntax-check-flagsmith`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=flagsmith env=production`
- `curl -fsS https://flags.lv3.org/health`
- `curl -I https://flags.lv3.org/`
- `curl -I https://flags.lv3.org/api/v1/projects/`

## Notes

- Protected integration files remain out of scope on this branch until the final synchronized merge-to-main step.
- If exact-main replay must wait because another workstream is actively mutating `docker-runtime-lv3`, capture the latest realistic live verification and record the remaining merge-to-main step explicitly.
