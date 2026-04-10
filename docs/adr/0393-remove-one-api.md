# ADR 0393: Remove One-API from the Platform

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.86
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Service Lifecycle, Operational Simplification
- Depends on: ADR 0389 (Service Decommissioning Procedure), ADR 0390 (Remove Open WebUI)
- Tags: lifecycle, decommissioning, one-api, llm-proxy, removal

---

## Context

One-API was introduced in ADR 0294 as a replacement for LiteLLM (ADR 0287,
deprecated after a supply-chain attack). Its role was to provide a unified
OpenAI-compatible API endpoint in front of Ollama with per-consumer API keys,
token quotas, and usage visibility.

### Why remove it now

The primary consumer of One-API was Open WebUI (removed in ADR 0390). With
Open WebUI gone, there are no active platform consumers routing LLM traffic
through One-API:

- **ServerClaw** referenced One-API in its bootstrap config but uses direct
  Ollama or external API keys in practice — the dependency was through Open
  WebUI's provider configuration, not a live runtime dependency.
- **Containers are already stopped** on docker-runtime-lv3 (confirmed
  pre-removal: `docker compose ps` returned empty).
- No active Dify workflows, agents, or platform services are documented as
  routing through One-API's endpoint (`http://100.64.0.1:8018/v1`).
- The Grafana dashboard and SLO rules exist but show no traffic.

### Removal scope

85 active file references across the codebase:

| Category | Files | Key items |
|---|---|---|
| Ansible roles | 9 | `one_api_runtime`, serverclaw bootstrap config |
| Playbooks | 2 | `one-api.yml` (collection + services/) |
| Inventory/config | 5 | platform_services, identity, TLS certs, main.yml |
| Config catalogs | 27 | capability, command, workflow, image, secret, health-probe, slo catalogs |
| Tests | 7 | role tests, playbook tests, integration refs |
| Scripts | 3 | bootstrap, observation tool, platform_ops |
| Documentation | 28 | 2 ADRs (→ Deprecated), workstreams |
| Versions | 1 | stack.yaml receipt |
| Workstreams | 2 | archived entries |

---

## Decision

Remove One-API from the platform following ADR 0389's phased procedure.

### Phase 1: Production Teardown

Containers already stopped. No active PostgreSQL database confirmed (secret
catalog lists `one_api_database_password` but no dedicated DB was provisioned
separately from the compose stack's bundled SQLite).

### Phase 2: Code Removal — automated + structured

```bash
# Dry-run
python3 scripts/decommission_service.py --service one_api

# Execute
python3 scripts/decommission_service.py --service one_api \
  --purge-code --confirm one_api
```

Followed by structured JSON/YAML cleanup (lessons from ADR 0390: line-level
removal breaks JSON; use targeted dict/list removal instead).

### Phase 3: Reconverge affected services

- `monitoring-stack` — remove Prometheus rules, Grafana dashboard, SLO records
- `database-dns` — no DNS record (private-only service)
- `keycloak` — no OIDC client (One-API used token auth, not SSO)

### Phase 4: Validate

```bash
# Zero active references
grep -rli --include="*.yml" --include="*.yaml" --include="*.json" \
  --include="*.py" --include="*.sh" \
  --exclude-dir=.git --exclude-dir=receipts --exclude-dir=docs \
  --exclude-dir=__pycache__ \
  -E "one.api|one_api|oneapi" \
  collections/ inventory/ config/ scripts/ tests/ playbooks/
# Expected: empty
```

---

## Consequences

**Positive:**
- Removes a dormant service with no active consumers
- Eliminates 4 secrets from the secret catalog
- Simplifies the LLM access path: consumers use Ollama directly or external APIs
- Reduces docker-runtime-lv3 resource footprint

**Negative / Trade-offs:**
- If a future service needs a unified LLM proxy, One-API would need to be
  re-introduced (or a replacement chosen). The ADR history preserves the
  rationale for the original choice.
- ServerClaw bootstrap config references will need updating to point directly
  at Ollama or a new proxy if LLM routing is needed.

---

## Related

- ADR 0389 — Service Decommissioning Procedure
- ADR 0390 — Remove Open WebUI (primary consumer removed first)
- ADR 0294 — One-API introduction (→ Deprecated)
- ADR 0287 — LiteLLM (already deprecated, supply-chain attack)
