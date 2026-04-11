# Workstream ws-0255-live-apply: ADR 0255 Live Apply From Latest `origin/main`

- ADR: [ADR 0255](../adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md)
- Title: repo-managed Matrix Synapse deployment, live apply, verification, and merge-safe evidence capture
- Status: live_applied
- Implemented In Repo Version: 0.177.85
- Live Applied In Platform Version: 0.130.58
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/adr-0255-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/adr-0255-live-apply`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-vm-baseline`, `adr-0026-dedicated-postgresql-vm-baseline`, `adr-0077-compose-runtime-secrets-injection`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md`, `docs/workstreams/ws-0255-live-apply.md`, `docs/runbooks/configure-matrix-synapse.md`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/uptime-kuma/monitors.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `playbooks/matrix-synapse.yml`, `playbooks/services/matrix-synapse.yml`, `collections/ansible_collections/lv3/platform/playbooks/matrix-synapse.yml`, `collections/ansible_collections/lv3/platform/roles/matrix_synapse_postgres/`, `collections/ansible_collections/lv3/platform/roles/matrix_synapse_runtime/`, `scripts/generate_platform_vars.py`, `scripts/validate_repo.sh`, `tests/test_generate_platform_vars.py`, `tests/test_matrix_synapse_playbook.py`, `tests/test_matrix_synapse_runtime_role.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- ship a repo-managed Matrix Synapse runtime on `docker-runtime` with PostgreSQL persistence on `postgres`
- publish `matrix.example.com` through the shared NGINX edge with TLS while keeping authentication inside Synapse instead of the shared edge-auth layer
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
- `inventory/host_vars/proxmox-host.yml`
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

- `matrix.example.com` resolves through the shared edge and returns Matrix client metadata over TLS
- `docker-runtime` runs the repo-managed Synapse compose stack with a stable signing key and repo-managed secrets
- `postgres` hosts the repo-managed Matrix Synapse database and login role
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
- `curl -fsS https://matrix.example.com/_matrix/client/versions`
- `curl -fsS http://100.64.0.1:8015/_matrix/client/versions`
- password-login verification for the repo-managed admin user against the live Matrix API

## Merge Criteria

- the Matrix Synapse repo surface validates cleanly and the dedicated playbook converges from the isolated worktree
- DNS, edge publication, PostgreSQL persistence, private controller proxying, and admin login all verify end to end
- the branch records ADR metadata, runbook updates, workstream status, and a structured live-apply receipt clearly enough for safe merge or direct mainline integration

## Outcome

- The exact-main integration finalized on repository version `0.177.85` and
  platform version `0.130.58` after rebasing onto the latest published
  `origin/main`, including the follow-up merge-marker commit that marked ADR
  0264 merged on main.
- The exact-main Matrix replay from release commit
  `cdf1b9a4adaaa35b048f7ecd41e4d6087c07e5cf` completed successfully with final
  recap `docker-runtime ok=131 changed=5 failed=0`,
  `localhost ok=18 changed=0 failed=0`,
  `nginx-edge ok=38 changed=3 failed=0`,
  `postgres ok=51 changed=0 failed=0`, and
  `proxmox-host ok=31 changed=4 failed=0`.
- A later exact-main monitoring replay from source commit
  `169d7e6549e539747d140497acd8a01e9049c330` corrected the public HTTPS/TLS
  assurance path by routing blackbox probes through the internal edge with a
  public hostname override, then completed successfully with final recap
  `backup ok=14 changed=0 failed=0`,
  `coolify ok=14 changed=0 failed=0`,
  `docker-build ok=46 changed=0 failed=0`,
  `docker-runtime ok=72 changed=2 failed=0`,
  `monitoring ok=397 changed=2 failed=0`,
  `nginx-edge ok=150 changed=3 failed=0`,
  `postgres ok=38 changed=0 failed=0`, and
  `proxmox-host ok=100 changed=0 failed=0`.
- Focused validation stayed green across both phases: the branch-local Matrix
  slice returned `26 passed in 1.26s`, `make syntax-check-matrix-synapse`
  passed, `make pre-push-gate` passed on the rebased workstream branch, and
  the exact-main public-edge assurance fix returned `16 passed in 0.34s` for
  `tests/test_https_tls_assurance_targets.py` plus
  `tests/test_monitoring_vm_role.py`.

## Mainline Integration Outcome

- The canonical mainline receipt is
  `receipts/live-applies/2026-03-29-adr-0255-matrix-synapse-mainline-live-apply.json`.
- That receipt supersedes the branch-local evidence in
  `receipts/live-applies/2026-03-29-adr-0255-matrix-synapse-live-apply.json`
  and the earlier exact-main candidate that predated the internal-edge HTTPS
  assurance correction.
- Shared integration files no longer remain pending for this ADR on main: the
  release surfaces, canonical truth, README status, and receipt pointers now
  all record ADR 0255 as live from `main`.

## Live Evidence

- `https://matrix.example.com/_matrix/client/versions` returned `status 200` from
  `server nginx` with `versions_count 20` and `unstable_features 34`.
- Password login against `https://matrix.example.com/_matrix/client/v3/login`
  returned `status 200` in `0.60s`, `user_id @ops:matrix.example.com`,
  `home_server matrix.example.com`, and well-known base
  `https://matrix.example.com/`; the controller-local login path on
  `http://100.64.0.1:8015/_matrix/client/v3/login` also returned `status 200`
  in `9.27s`.
- `http://100.64.0.1:8015/_matrix/client/versions` returned `status 200` with
  `server Synapse/1.150.0`, and `sudo ss -ltnp` on `proxmox-host` confirmed
  the controller listener is bound on `100.64.0.1:8015`.
- `sudo docker compose --file /opt/matrix-synapse/docker-compose.yml ps
  --format json` on `docker-runtime` showed
  `matrixdotorg/synapse:v1.150.0` in `running` state with status
  `Up 3 hours (healthy)`, plus the `openbao-agent` sidecar healthy.
- Prometheus on `monitoring` reported
  `probe_success{job="https-tls-blackbox",assurance_id="matrix-synapse-public"} = 1`,
  `up{job="matrix_synapse-readiness"} = 1`, and
  `up{job="matrix_synapse-liveness"} = 1`; the live target file now points at
  `https://10.10.10.10:443/_matrix/client/versions` with
  `probe_hostname: matrix.example.com`, and the live rule file still carries the
  `matrix-synapse-public` alert definitions.
