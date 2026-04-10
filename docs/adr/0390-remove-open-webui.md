# ADR 0390: Remove Open WebUI from the Platform

**Status:** Accepted
**Decision Date:** 2026-04-10
**Concern:** Service Lifecycle, Operational Simplification
**Depends on:** ADR 0389 (Service Decommissioning Procedure)

---

## Context

Open WebUI was introduced in ADR 0060 as the operator and agent workbench
for interacting with LLMs (Ollama, OpenAI-compatible APIs). Over time it
accumulated significant integration surface:

- Keycloak OIDC client for SSO
- Dedicated NGINX edge publication
- SearXNG web search integration
- Ollama backend connection
- RAG pipeline with platform context injection (ADR 0377)
- ServercClaw tool surface (ADR 0378)
- Grafana dashboard + SLO alerting
- PostgreSQL database

The service is no longer needed and should be cleanly removed following
the procedure defined in ADR 0389.

### Removal scope

~189 files reference Open WebUI across the codebase:

| Category | Files | Key items |
|----------|-------|-----------|
| Ansible roles | 4 | `open_webui_runtime`, keycloak client tasks |
| Playbooks | 8 | open-webui.yml (collection + root + services) |
| Inventory/config | 6 | platform_services, identity, TLS certs |
| Config catalogs | 23 | dependency-graph, capability, command, workflow, image, secret catalogs |
| Generated config | 2 | DNS declarations, SSO clients |
| Monitoring | 5 | alertmanager rules, Grafana dashboard, SLO targets/rules |
| Tests | 7 | role tests, playbook tests, integration refs |
| Documentation | 25 | 10 ADRs (→ Deprecated), workstreams, guides |
| Workstreams | 10 | archived + completed entries |
| Scripts | 6 | homepage, platform_context, observation tool |
| Release notes | 63 | historical entries (preserve) |
| Build artifacts | 32 | manifest, receipts, evidence |
| versions/stack.yaml | 1 | receipt entry |

---

## Decision

Remove Open WebUI from the platform following ADR 0389's phased procedure.

### Phase 1: Production Teardown

```bash
# Stop containers on docker-runtime-lv3
ssh docker-runtime-lv3 "cd /opt/lv3/open-webui && docker compose down --remove-orphans"

# Remove NGINX site config and reconverge public-edge
# Remove DNS record from dns-declarations.yaml and reconverge database-dns
# Remove Keycloak OIDC client (keycloak_runtime/tasks/open_webui_client.yml)
# Drop PostgreSQL database: open_webui (on postgres-lv3)
```

### Phase 2: Code Removal — automated

```bash
# Dry-run (shows plan as JSON — 1 dir, 8 files, 41 reference files, catalogs)
python3 scripts/decommission_service.py --service open_webui

# Execute
python3 scripts/decommission_service.py --service open_webui \
  --purge-code --confirm open_webui
```

The script automatically:
- Deletes `open_webui_runtime` role directory
- Deletes 8 files (playbooks, keycloak client, alertmanager, grafana, tests)
- Removes `open_webui` from `service-capability-catalog.json` (structured rewrite)
- Cleans 41 config/inventory/script files of all `open_webui`/`open-webui` references
- Deprecates ADRs 0060, 0341, 0377, 0378
- Removes `open_webui` receipt from `versions/stack.yaml`
- Regenerates platform manifest and discovery artifacts

**Preserved as-is** (historical records): changelog, release notes, receipts.

### Phase 4: Converge affected services

After code removal, reconverge:
- `public-edge` — to remove NGINX upstream/server blocks
- `database-dns` — to remove DNS records
- `keycloak` — to remove the OIDC client
- `monitoring-stack` — to reload alert rules and dashboards

---

## Validation

```bash
# No active references outside docs/changelog/receipts
grep -ri "open.webui" \
  collections/ansible_collections/lv3/platform/roles/*/defaults/ \
  collections/ansible_collections/lv3/platform/roles/*/tasks/ \
  collections/ansible_collections/lv3/platform/roles/*/templates/ \
  inventory/ config/ tests/ scripts/ \
  | wc -l
# Expected: 0

# Platform manifest regenerates cleanly
python scripts/platform_manifest.py --write
git diff --stat build/platform-manifest.json
# Expected: only open_webui removal

# No dangling NGINX upstream
grep -r "open.webui" config/generated/ | wc -l
# Expected: 0
```

---

## Consequences

**Positive:**
- Reduces operational surface by one service (containers, monitoring, backups,
  OIDC client, database, NGINX routes)
- Frees resources on docker-runtime-lv3 (RAM, CPU, disk)
- Simplifies dependency graph — removes Ollama/SearXNG coupling
- ~189 fewer files to maintain

**Negative / Trade-offs:**
- Operators lose the built-in LLM chat interface (can use alternatives like
  Dify, direct API access, or external clients)
- Historical ADR/workstream references remain but point to deprecated service

---

## Related

- ADR 0389 — Service Decommissioning Procedure (general process)
- ADR 0060 — Open WebUI introduction (→ Deprecated)
- ADR 0341 — Open WebUI Keycloak OIDC (→ Deprecated)
- ADR 0377 — Open WebUI Platform Knowledge Integration (→ Deprecated)
- ADR 0378 — ServercClaw Tool Surface in Open WebUI (→ Deprecated)
