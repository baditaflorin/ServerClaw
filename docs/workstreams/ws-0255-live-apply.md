# Workstream ws-0255-live-apply: ADR 0255 Live Apply From Latest `origin/main`

- ADR: [ADR 0255](../adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md)
- Title: repo-managed Matrix Synapse deployment, live apply, verification, and merge-safe evidence capture
- Status: live_applied
- Implemented In Repo Version: not yet
- Live Applied In Platform Version: not yet
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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
- `100.64.0.1:8015` proxies the private controller path to the Synapse client and admin API listener
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
- `curl -fsS http://100.64.0.1:8015/_matrix/client/versions`
- password-login verification for the repo-managed admin user against the live Matrix API

## Merge Criteria

- the Matrix Synapse repo surface validates cleanly and the dedicated playbook converges from the isolated worktree
- DNS, edge publication, PostgreSQL persistence, private controller proxying, and admin login all verify end to end
- the branch records ADR metadata, runbook updates, workstream status, and a structured live-apply receipt clearly enough for safe merge or direct mainline integration

## Outcome

- After rebasing onto `origin/main` commit
  `8871117b40466b7907a33992f44ca7d83a3e9409`, the branch replay succeeded from
  source commit `450a8cde9b88c0f29e7c6feddcec5c38bf97667b` with repository
  version context `0.177.83` and integrated platform baseline `0.130.57`.
- `make converge-matrix-synapse` completed successfully with final recap
  `docker-runtime-lv3 ok=128 changed=2 failed=0`,
  `localhost ok=18 changed=0 failed=0`,
  `nginx-lv3 ok=39 changed=5 failed=0`,
  `postgres-lv3 ok=51 changed=0 failed=0`, and
  `proxmox_florin ok=31 changed=4 failed=0`.
- The matching `make converge-monitoring` replay also completed successfully so
  the new Matrix HTTPS/TLS assurance artifacts became live, with final recap
  `backup-lv3 ok=14 changed=0 failed=0`,
  `coolify-lv3 ok=14 changed=0 failed=0`,
  `docker-build-lv3 ok=46 changed=0 failed=0`,
  `docker-runtime-lv3 ok=72 changed=2 failed=0`,
  `monitoring-lv3 ok=400 changed=11 failed=0`,
  `nginx-lv3 ok=150 changed=3 failed=0`,
  `postgres-lv3 ok=38 changed=0 failed=0`, and
  `proxmox_florin ok=101 changed=3 failed=0`.
- Focused Matrix regression coverage and the full repository automation gate
  passed on the rebased branch head: `26` targeted tests passed, `make
  syntax-check-matrix-synapse` passed, the HTTPS/TLS assurance and diagram
  generators were current, and `make pre-push-gate` completed successfully.
- Protected mainline integration surfaces still remain pending from this branch:
  `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, release-note
  surfaces, and the canonical exact-main receipt after merge to `main`.

## Live Evidence

- `https://matrix.lv3.org/_matrix/client/versions` returned `status 200` from
  `server nginx` with `versions_count 20`.
- Password login against `https://matrix.lv3.org/_matrix/client/v3/login`
  returned `status 200`, `user_id @ops:matrix.lv3.org`,
  `home_server matrix.lv3.org`, and well-known base
  `https://matrix.lv3.org/`.
- `http://100.64.0.1:8015/_matrix/client/versions` returned `status 200` with
  `server Synapse/1.150.0`, and `sudo ss -ltnp` on `proxmox_florin` confirmed
  the controller listener is bound on `100.64.0.1:8015`.
- `sudo docker compose --file /opt/matrix-synapse/docker-compose.yml ps
  --format json` on `docker-runtime-lv3` showed
  `matrixdotorg/synapse:v1.150.0` in `running` state with status
  `Up About an hour (healthy)`, plus the `openbao-agent` sidecar healthy.
- Prometheus on `monitoring-lv3` reported `matrix_rule_loaded True` and
  `matrix_target_active True` for assurance id `matrix-synapse-public`, and the
  live files were present at `/etc/prometheus/file_sd/https-tls-targets.yml`
  and `/etc/prometheus/rules/https-tls-alerts.yml`.
