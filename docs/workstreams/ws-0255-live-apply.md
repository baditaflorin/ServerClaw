# Workstream ws-0255-live-apply: ADR 0255 Live Apply From Latest `origin/main`

- ADR: [ADR 0255](../adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md)
- Title: repo-managed Matrix Synapse deployment, live apply, verification, and merge-safe evidence capture
- Status: in_progress
- Branch: `codex/adr-0255-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0255-live-apply`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-vm-baseline`, `adr-0026-dedicated-postgresql-vm-baseline`, `adr-0077-compose-runtime-secrets-injection`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md`, `docs/workstreams/ws-0255-live-apply.md`, `docs/runbooks/configure-matrix-synapse.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/uptime-kuma/monitors.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `playbooks/matrix-synapse.yml`, `playbooks/services/matrix-synapse.yml`, `collections/ansible_collections/lv3/platform/playbooks/matrix-synapse.yml`, `collections/ansible_collections/lv3/platform/roles/matrix_synapse_postgres/`, `collections/ansible_collections/lv3/platform/roles/matrix_synapse_runtime/`, `scripts/generate_platform_vars.py`, `scripts/validate_repo.sh`, `tests/test_generate_platform_vars.py`, `tests/test_matrix_synapse_playbook.py`, `tests/test_matrix_synapse_runtime_role.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- ship a repo-managed Matrix Synapse runtime on `docker-runtime-lv3` with PostgreSQL persistence on `postgres-lv3`
- publish `matrix.lv3.org` through the shared NGINX edge with TLS while keeping authentication inside Synapse instead of the shared edge-auth layer
- expose a private Tailscale controller proxy on the Proxmox host for governed operator and automation access
- validate the repo automation surface, perform the live apply from the latest realistic `origin/main` base, and capture structured receipts and verification evidence

## Non-Goals

- implementing Matrix federation, bridge adapters, or delegated capability policy in the same workstream
- adding a browser client such as Element to the platform in the same ADR
- changing protected integration files until the final merge-to-main step

## Expected Repo Surfaces

- `docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md`
- `docs/workstreams/ws-0255-live-apply.md`
- `docs/runbooks/configure-matrix-synapse.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/subdomain-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/uptime-kuma/monitors.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `playbooks/matrix-synapse.yml`
- `playbooks/services/matrix-synapse.yml`
- `collections/ansible_collections/lv3/platform/playbooks/matrix-synapse.yml`
- `collections/ansible_collections/lv3/platform/roles/matrix_synapse_postgres/`
- `collections/ansible_collections/lv3/platform/roles/matrix_synapse_runtime/`
- `scripts/generate_platform_vars.py`
- `scripts/validate_repo.sh`
- `tests/test_generate_platform_vars.py`
- `tests/test_matrix_synapse_playbook.py`
- `tests/test_matrix_synapse_runtime_role.py`

## Expected Live Surfaces

- `matrix.lv3.org` resolves through the shared edge and returns Matrix client metadata over TLS
- `docker-runtime-lv3` runs the repo-managed Synapse compose stack with a stable signing key and repo-managed secrets
- `postgres-lv3` hosts the repo-managed Matrix Synapse database and login role
- `100.64.0.1:8014` proxies the private controller path to the Synapse client and admin API listener
- the repo-managed admin account can authenticate successfully against the live Synapse server

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_generate_platform_vars.py tests/test_matrix_synapse_playbook.py tests/test_matrix_synapse_runtime_role.py`
- `python3 scripts/service_catalog.py --validate`
- `python3 scripts/service_completeness.py --service matrix_synapse`
- `python3 scripts/live_apply_receipts.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `make syntax-check-matrix-synapse`
- `make pre-push-gate`
- `HETZNER_DNS_API_TOKEN=... make converge-matrix-synapse`
- `curl -fsS https://matrix.lv3.org/_matrix/client/versions`
- `curl -fsS http://100.64.0.1:8014/_matrix/client/versions`
- password-login verification for the repo-managed admin user against the live Matrix API

## Merge Criteria

- the Matrix Synapse repo surface validates cleanly and the dedicated playbook converges from the isolated worktree
- DNS, edge publication, PostgreSQL persistence, private controller proxying, and admin login all verify end to end
- the branch records ADR metadata, runbook updates, workstream status, and a structured live-apply receipt clearly enough for safe merge or direct mainline integration

## Outcome

- Pending implementation, live apply, and final mainline integration.
