# Workstream ADR 0146: Langfuse For Agent Observability

- ADR: [ADR 0146](../adr/0146-langfuse-for-agent-observability.md)
- Title: Self-hosted Langfuse runtime, bootstrap project contract, and live trace verification path for agent observability
- Status: live_applied
- Implemented In Repo Version: 0.163.0
- Implemented In Platform Version: 0.130.14
- Implemented On: 2026-03-26
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

## Merge Criteria

- Langfuse is deployed entirely from repo-managed automation
- the public service, runtime secrets, health probe, workflow, and dependency contracts are all represented in-repo
- the live smoke trace is observable through the Langfuse public API and the direct UI trace path
- ADR and runbook status are finalized to implemented

## Outcome

- Repo implementation completed for release `0.163.0` on `2026-03-26`.
- Live verification completed on the public production hostname: `https://langfuse.lv3.org/api/public/health` returned `200`, the seeded `lv3-agent-observability` project was reachable through the public API, and the smoke verifier ingested trace `4080b556f5c041e3a6afc28f37b99d41` with direct UI resolution at `https://langfuse.lv3.org/project/lv3-agent-observability/traces/4080b556f5c041e3a6afc28f37b99d41`.
- The final rollout required follow-up fixes after the first live apply attempt: canonical Langfuse topology generation, restart-safe edge certificate recovery defaults, URL-safe PostgreSQL credential handling, import-safe smoke helper loading, and Redis volume ownership pinning so background persistence no longer blocks trace ingestion.

## Notes For The Next Assistant

- The controller-local Langfuse bootstrap artifacts remain under `.local/langfuse/`, including the bootstrap-user password plus the project public and secret keys used by `scripts/langfuse_trace_smoke.py`.
- The Hetzner DNS token used for certificate issuance and edge publication is stored controller-locally at `.local/hetzner/dns-api-token.txt`.
