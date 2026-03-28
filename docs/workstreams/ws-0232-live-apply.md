# Workstream WS-0232: Nomad Live Apply

- ADR: [ADR 0232](../adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- Title: Live apply and end-to-end verification for the private Nomad scheduler
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0232-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0232-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0179-service-redundancy-tier-matrix`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none
- Shared Surfaces: `Makefile`, `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-nomad.md`, `docs/workstreams/ws-0232-live-apply.md`, `workstreams.yaml`, `playbooks/groups/automation.yml`, `playbooks/nomad.yml`, `playbooks/services/nomad.yml`, `collections/ansible_collections/lv3/platform/roles/nomad_cluster_member/`, `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/`, `config/nomad/jobs/`, `config/ansible-execution-scopes.yaml`, `config/service-capability-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/health-probe-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/dependency-graph.json`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `tests/test_nomad_playbook.py`, `tests/test_nomad_cluster_roles.py`, `tests/test_generate_platform_vars.py`, `tests/test_proxmox_tailscale_proxy_role.py`, `receipts/live-applies/`

## Scope

- implement the repo-managed Nomad server, client, TLS, ACL, and smoke-job automation required by ADR 0232
- expose the private controller entrypoint for Nomad through the Proxmox host Tailscale TCP proxy catalog
- live-apply the scheduler from an isolated latest-`origin/main` worktree without mutating protected integration files on this branch
- verify both branch-local validation and the production automation path end to end
- record live evidence and leave merge-safe notes for the final `main` integration step

## Expected Repo Surfaces

- `playbooks/nomad.yml`
- `playbooks/groups/automation.yml`
- `playbooks/services/nomad.yml`
- `Makefile`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_member/`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/`
- `config/nomad/jobs/lv3-nomad-smoke-service.nomad.hcl`
- `config/nomad/jobs/lv3-nomad-smoke-batch.nomad.hcl`
- `docs/runbooks/configure-nomad.md`
- `docs/workstreams/ws-0232-live-apply.md`
- `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- `monitoring-lv3` runs the private Nomad server and mirrors the bootstrap management token
- `docker-runtime-lv3` and `docker-build-lv3` run Nomad clients with the Docker driver enabled
- the controller can reach the Nomad API at `https://100.64.0.1:8013`
- the repo-managed smoke service is running on `docker-build-lv3` and serves the expected verification page on `127.0.0.1:18180`
- the repo-managed smoke batch job can be dispatched and completes successfully on `docker-runtime-lv3`

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_nomad_playbook.py tests/test_nomad_cluster_roles.py tests/test_generate_platform_vars.py tests/test_proxmox_tailscale_proxy_role.py -q`
- `make syntax-check-nomad`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- `make live-apply-service service=nomad env=production`
- controller-side `nomad node status` through the Tailscale proxy plus guest-side smoke service checks on `monitoring-lv3` and `docker-build-lv3`

## Outcome

- pending live apply

## Mainline Integration

- this workstream intentionally leaves `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, and the top-level README status summary untouched until the final latest-main integration step
- after branch-local live apply verification, the remaining protected-file work should be limited to `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, `RELEASE.md`, release notes, and any regenerated canonical truth that is only allowed on `main`

## Notes For The Next Assistant

- if the first live apply fails, check `lv3-nomad.service` on the affected guest before assuming the cluster bootstrap or smoke jobs are wrong
- the client nodes need Nomad RPC open in both directions with `monitoring-lv3`; keep the branch-local firewall rules aligned with that cluster contract
