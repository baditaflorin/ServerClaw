# ADR 0151: n8n for Webhook and API Integration Automation

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.148.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Date: 2026-03-25

## Context

The platform already has repo-managed ingress, shared SSO, compose runtime automation, and PostgreSQL-backed control-plane services. What it lacks is a dedicated workflow engine for:

- inbound webhook handling from external systems
- low-code API integration orchestration
- operator-owned automation that can bridge SaaS APIs without embedding every integration as a bespoke repo-side script

The next phase in the infrastructure plan explicitly calls out ingress, security, backup, and API automation work. A dedicated automation surface needs to fit the existing platform boundaries instead of bypassing them:

- runtime state should stay repo-managed
- secrets should flow through the existing OpenBao compose-secret path
- the public editor should not be exposed anonymously
- webhook endpoints must still be reachable without forcing browser SSO on machine callers

## Decision

We run `n8n` as a repo-managed compose service on `docker-runtime-lv3`, backed by PostgreSQL on `postgres-lv3`, and published at `https://n8n.lv3.org`.

### Runtime shape

- service id: `n8n`
- runtime host: `docker-runtime-lv3`
- database backend: PostgreSQL on `postgres-lv3`
- public hostname: `n8n.lv3.org`
- pinned image: `docker.n8n.io/n8nio/n8n:2.2.6@sha256:1ecc41c012acc5a425e43ff4b87193d8c08d00832876df367656eb7e5ee7fc5b`
- internal listen port: `5678`
- persistent application data: `/opt/n8n/data`

The runtime is converged through `roles/n8n_postgres`, `roles/n8n_runtime`, and `playbooks/n8n.yml`.

### Access boundary

The editor and management surface at `n8n.lv3.org` are protected by the shared repo-managed oauth2-proxy and Keycloak edge flow.

Because webhook callers are machine clients, the edge route deliberately leaves the following paths unauthenticated:

- `/healthz`
- `/webhook/`
- `/webhook-test/`
- `/webhook-waiting/`

This keeps the operator-facing editor behind edge authentication while preserving external webhook reachability.

### Secret and bootstrap model

The implementation generates and manages:

- a PostgreSQL password for the `n8n` database role
- an `N8N_ENCRYPTION_KEY`
- an initial owner password mirrored to the controller

Database and runtime encryption secrets are injected through the existing OpenBao compose-env sidecar pattern. The initial owner account is bootstrapped through `POST /rest/owner/setup`.

### Workflow-management boundary

Repo converge does not automatically import workflows into the live n8n instance.

The n8n CLI import path can deactivate imported workflows, which makes automatic sync unsafe for active automation. Workflow export and import remain an explicit operator action documented in the runbook.

## Consequences

### Positive

- The platform gains a repo-managed webhook and API integration engine without introducing ad hoc runtime drift.
- Webhooks can be reached publicly while the editor stays behind the shared SSO edge boundary.
- n8n runtime secrets reuse the existing OpenBao sidecar contract already used by other compose services.
- PostgreSQL-backed persistence avoids the durability limits of the default SQLite deployment path.

### Trade-offs

- The public hostname carries mixed auth semantics by path: the editor is OIDC-gated while webhook routes are intentionally public.
- Operators still need to manage workflow content explicitly; the repo does not yet own n8n workflow definitions as a safe converge artifact.
- Native n8n SSO remains out of scope because the practical upstream OIDC path is not the right fit for the current repo-managed open-source deployment boundary.

## Repository Verification

The repository implementation was validated on 2026-03-26 with:

- `make syntax-check-n8n`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_n8n_playbook.py tests/test_n8n_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/uptime_contract.py --check`
- `uvx --from pyyaml python scripts/subdomain_exposure_audit.py --check-registry`
- `scripts/validate_repo.sh yaml role-argument-specs shell json compose-runtime-envs health-probes`

Live verification from `main` completed successfully on 2026-03-26.

## Live Apply Note

The first live apply attempt from `main` on 2026-03-25 did not complete.

- Hetzner DNS write calls for the new `n8n.lv3.org` record returned the provider brownout response during the documented `11:00` to `13:00` UTC weekday shutdown window.
- During the same window, the Proxmox host was unreachable from the controller on both `100.118.189.95:22` and `65.108.75.123:22`, and `https://proxmox.lv3.org:8006/api2/json` timed out.

The successful rerun from current `main` completed on 2026-03-26 after narrowing the service playbook to the n8n-specific DNS record, pinning the runtime database host to the PostgreSQL primary guest address, recovering Docker bridge-chain startup failures on `docker-runtime-lv3`, and regenerating the repo-managed static portal artifacts expected by shared edge publication.

- `docker-runtime-lv3` rendered `DB_POSTGRESDB_HOST=10.10.10.50` in `/run/lv3-secrets/n8n/runtime.env`.
- Local `http://127.0.0.1:5678/healthz` and `http://127.0.0.1:5678/healthz/readiness` both returned `{"status":"ok"}`.
- Public `https://n8n.lv3.org/healthz` returned `HTTP 200` through the shared NGINX edge.

## Related ADRs

- ADR 0025: Compose-managed runtime stacks
- ADR 0026: Dedicated PostgreSQL VM baseline
- ADR 0043: OpenBao for control-plane secrets
- ADR 0056: Keycloak SSO broker
- ADR 0077: Compose runtime secrets injection
