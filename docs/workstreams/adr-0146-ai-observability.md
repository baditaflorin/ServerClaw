# Workstream ADR 0146: Langfuse For Agent Observability

- ADR: [ADR 0146](../adr/0146-langfuse-for-agent-observability.md)
- Title: Self-hosted Langfuse runtime, bootstrap project contract, and live trace verification path for agent observability
- Status: in_progress
- Implemented In Repo Version: TBD
- Implemented In Platform Version: TBD
- Implemented On: TBD
- Branch: `codex/adr-0146-ai-observability`
- Worktree: `.worktrees/adr-0146-ai-observability`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0056-keycloak-sso`, `adr-0075-service-capability-catalog`, `adr-0077-compose-secrets-injection`
- Conflicts With: none
- Shared Surfaces: `playbooks/langfuse.yml`, `collections/ansible_collections/lv3/platform/roles/langfuse_runtime/`, `collections/ansible_collections/lv3/platform/roles/langfuse_postgres/`, `config/service-capability-catalog.json`, `inventory/host_vars/proxmox_florin.yml`

## Scope

- add ADR 0146 for self-hosted Langfuse agent observability
- deploy Langfuse on `docker-runtime-lv3` with PostgreSQL on `postgres-lv3`
- publish `langfuse.lv3.org` through the shared NGINX edge
- provision the Keycloak OIDC client for Langfuse sign-in
- seed a repo-managed bootstrap org, project, API key pair, and bootstrap user
- add the repo-side smoke verifier and config loader for future Langfuse-enabled agent runtimes
- verify one live synthetic trace through both the public API and the Langfuse UI path

## Non-Goals

- migrating Grafana Tempo service traces into Langfuse
- instrumenting every existing repo workflow in the same change
- exposing Langfuse anonymously on the public internet

## Expected Repo Surfaces

- `docs/adr/0146-langfuse-for-agent-observability.md`
- `docs/runbooks/configure-langfuse.md`
- `playbooks/langfuse.yml`
- `collections/ansible_collections/lv3/platform/roles/langfuse_runtime/`
- `collections/ansible_collections/lv3/platform/roles/langfuse_postgres/`
- `scripts/langfuse_trace_smoke.py`
- `platform/llm/observability.py`
- the canonical service, secret, image, health, workflow, dependency, and topology catalogs

## Expected Live Surfaces

- `https://langfuse.lv3.org`
- Langfuse bootstrap project `lv3-agent-observability`
- repo-managed project API keys mirrored under `.local/langfuse/`
- one successful live synthetic trace verification with a direct Langfuse trace URL

## Verification

- `make syntax-check-langfuse`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_langfuse_observability.py tests/test_keycloak_runtime_role.py tests/test_compose_runtime_secret_injection.py -q`
- `uv run --with langfuse --with requests python scripts/langfuse_trace_smoke.py --base-url https://langfuse.lv3.org --project-id lv3-agent-observability --bootstrap-email baditaflorin@gmail.com --bootstrap-password-file .local/langfuse/bootstrap-user-password.txt`

## Current Blockers

- As of 2026-03-26, Langfuse remains healthy on `docker-runtime-lv3` and the bootstrap project API remains reachable on the internal service endpoint, but the shared `nginx-lv3` publication is still incomplete.
- `https://langfuse.lv3.org` no longer serves the generic edge page. It now redirects to `https://nginx.lv3.org/`, which confirms partial edge publication, but the host is still using the `nginx.lv3.org` certificate and does not include `langfuse.lv3.org` as a SAN.
- Controller SSH still times out to `proxmox_florin` on `65.108.75.123:22`, `100.64.0.1:22`, and the previously observed `100.118.189.95:22`. `https://proxmox.lv3.org:8006` also times out from the controller.
- Controller-local Tailscale is currently logged out because `https://headscale.lv3.org` presents the wrong certificate. The observed SAN set includes `nginx.lv3.org` and omits `headscale.lv3.org`, so the private management path cannot currently be re-established from this controller.
- The controller's observed public IPv4 during the latest retry was `90.95.35.115`. If public-IP-based SSH filtering is in use on the Proxmox host firewall, that source may need to be temporarily allowed before publication can continue.

## Merge Criteria

- Langfuse is deployed entirely from repo-managed automation
- the public service, runtime secrets, health probe, workflow, and dependency contracts are all represented in-repo
- the live smoke trace is observable through the Langfuse public API and the direct UI trace path
- ADR and runbook status are finalized to implemented
