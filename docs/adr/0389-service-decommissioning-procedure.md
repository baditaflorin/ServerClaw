# ADR 0389: Standard Procedure for Decommissioning a Platform Service

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.79
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Operational Hygiene, Service Lifecycle, Codebase Maintainability
- Depends on: ADR 0373 (Service Registry), ADR 0385 (IoC Library Refactor)
- Tags: lifecycle, decommissioning, automation, scripts, procedures

## Context

The platform has grown to 70+ services. As priorities shift, some services
become redundant, replaced by alternatives, or no longer needed. There is
currently no documented procedure for cleanly removing a service from the
platform. Without a standard process, partial removals leave orphaned
configuration, broken references, and ghost entries in monitoring and
deployment catalogs.

A service removal touches many surfaces:

1. **Ansible roles** — the runtime role, postgres client role, Keycloak
   client tasks
2. **Playbooks** — service-specific and group playbooks, collection wrappers
3. **Inventory** — group_vars, host_vars, platform_services.yml, identity.yml
4. **Configuration catalogs** — dependency-graph, service-capability,
   command-catalog, workflow-catalog, api-gateway-catalog, image-catalog,
   secret-catalog, service-redundancy, one-api bootstrap
5. **Generated config** — DNS declarations, SSO clients, TLS cert list
6. **Monitoring** — Alertmanager rules, Grafana dashboards, Prometheus
   targets/rules (SLO)
7. **Tests** — role tests, playbook tests, integration tests
8. **Documentation** — ADRs (status → Deprecated), runbooks, workstreams,
   operator guides, repository map
9. **Build artifacts** — platform-manifest.json, onboarding files
10. **Receipts** — live-apply evidence, image scans, gate bypasses
11. **versions/stack.yaml** — latest_receipts entry
12. **NGINX edge** — upstream blocks, server blocks, location blocks
13. **Docker runtime** — compose files, volumes, networks on the target VM
14. **Database** — PostgreSQL database, role, and pg_hba entries
15. **Secrets** — OpenBao paths, .local credential files
16. **Changelog / Release notes** — historical references (leave as-is)

---

## Decision

### Phase 0: Pre-flight

1. **Create the decommissioning ADR** — records why the service is being
   removed, what replaces it (if anything), and any data retention
   obligations.
2. **Open a workstream** — branch `claude/<service>-decommission`.
3. **Notify stakeholders** — if the service has active users, communicate
   the timeline.

### Phase 1: Production Teardown (on target VMs)

Run in order on the production host:

```bash
# 1. Stop and remove containers
ssh <vm> "cd /opt/lv3/<service> && docker compose down --remove-orphans"

# 2. Remove NGINX upstream/server blocks
# (converge public-edge after removing the site config)

# 3. Remove DNS records
# (converge database-dns after removing from dns-declarations.yaml)

# 4. Remove Keycloak OIDC client
# (via Keycloak admin API or by removing the client task and reconverging)

# 5. Drop PostgreSQL database and role (if dedicated)
# CAUTION: Export data first if retention is required
```

### Phase 2: Code Removal — automated via `decommission_service.py`

The code purge is fully automated. No AI agent or manual checklist needed.

```bash
# Dry-run — shows exactly what will be deleted, cleaned, and regenerated
python3 scripts/decommission_service.py --service <service_id>

# Execute code purge (deterministic, CPU-only, no tokens burned)
python3 scripts/decommission_service.py --service <service_id> \
  --purge-code --confirm <service_id>
```

The script handles all surfaces automatically:

| Surface | Action |
|---------|--------|
| `roles/<service>_runtime/` | Delete directory |
| `roles/<service>_postgres/` | Delete directory |
| `keycloak_runtime/tasks/<service>_client.yml` | Delete file |
| Collection + root playbooks | Delete files |
| Playbook vars | Delete files |
| Alertmanager rules | Delete file |
| Grafana dashboards | Delete file |
| Test files | Delete files |
| `service-capability-catalog.json` | Remove entry (structured JSON rewrite) |
| `subdomain-catalog.json` | Remove entry (structured JSON rewrite) |
| ~40 config/inventory/script files | Remove lines referencing service |
| `versions/stack.yaml` | Remove receipt entry |
| ADRs mentioning service in title | Set status to Deprecated |
| Platform manifest + discovery artifacts | Regenerate |

**Extending the script:** When a new catalog or integration surface is
added to the platform, add its path to `decommission_service.py` so future
removals catch it automatically. The script uses `grep` to find references,
so most new surfaces are discovered without code changes.

### Phase 3: Validate

```bash
# Verify no active references remain
grep -ri "<service_id>" \
  collections/ansible_collections/lv3/platform/roles/*/defaults/ \
  collections/ansible_collections/lv3/platform/roles/*/tasks/ \
  inventory/ config/ tests/ scripts/ \
  | grep -v "docs/\|changelog\|receipts/\|release-notes/" | wc -l
# Expected: 0

# Run validation
make validate
```

### Phase 4: Merge and Record

Follow the standard merge-to-main checklist (CLAUDE.md §4). The commit
message should reference the decommissioning ADR.

### What to preserve

- **Release notes and changelog** — historical entries stay as-is. They
  document what happened, not what exists now.
- **Receipts** — live-apply evidence and image scans are historical records.
  Keep them unless they cause validation noise.
- **ADRs** — set status to `Deprecated` with a note pointing to the
  decommissioning ADR. Do not delete ADRs.

---

## Validation

After the decommissioning merge:

```bash
# No references to the service in active configuration
grep -ri "<service_name>" \
  collections/ansible_collections/lv3/platform/roles/*/defaults/ \
  collections/ansible_collections/lv3/platform/roles/*/tasks/ \
  inventory/ config/ \
  | grep -v "docs/" | grep -v "changelog" | grep -v "receipts/" \
  | wc -l
# Expected: 0 (excluding docs, changelog, receipts)

# Platform manifest regenerates cleanly
python scripts/platform_manifest.py --write && git diff --stat
# Expected: no unexpected changes

# Tests pass
make validate
```

---

## Consequences

**Positive:**
- Consistent, repeatable process prevents orphaned configuration
- Checklist ensures no surface is missed during removal
- Historical records are preserved while active configuration is clean

**Negative / Trade-offs:**
- Removing a deeply integrated service is inherently a large changeset
- Requires production access for Phase 1 teardown steps

---

## Related

- ADR 0373 — Service Registry (platform_services.yml is the canonical service list)
- ADR 0385 — IoC Library Refactor (centralized configuration aids removal)
