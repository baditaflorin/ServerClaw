# ADR 0404: Service Lifecycle Contract — BEGIN/END Markers as Platform Standard

**Status:** Accepted
**Decision Date:** 2026-04-10
**Concern:** Service Lifecycle, Platform Tooling
**Depends on:** ADR 0396 (Deterministic Service Decommissioning), ADR 0402 (JupyterHub Removal)

---

## Context

ADR 0396 established `decommission_service.py` as a CPU-only, deterministic decommission tool.
The postmortem from ADR 0402 (JupyterHub removal) identified seven gaps, the most impactful being:

1. **Gap 2** — `platform_services.yml` retained an orphaned body block after the key was removed by
   the YAML topology handler. The service body lived outside the scanned topology section.
2. **Gap 3** — `keycloak_runtime/defaults/main.yml` and `keycloak_runtime/tasks/main.yml` are shared
   role files; the decommission script did not scan them for per-service blocks.

Both gaps share the same root cause: important service configuration lived in hand-authored,
structurally-nested YAML files with no machine-readable block boundaries.

The fix is to establish `# BEGIN SERVICE: <id>` / `# END SERVICE: <id>` YAML comments as the
**platform standard contract** for marking per-service blocks in any hand-authored YAML file.

---

## Decision

### 1. The Contract

Every hand-authored YAML file that contains per-service blocks **must** wrap each block with:

```yaml
# BEGIN SERVICE: <service_id>
<service block content>
# END SERVICE: <service_id>
```

The service_id **must exactly match** the identifier used in `config/service-capability-catalog.json`.

This applies to:
- `inventory/group_vars/all/platform_services.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- Any future shared YAML file where multiple services share a single file

### 2. Decommission Integration

`decommission_service.py` uses `_remove_yaml_block_markers()` as the removal strategy for these files.
New CATALOG_REGISTRY types:

| type | file | handler |
|------|------|---------|
| `yaml_marker_block` | `platform_services.yml` | `_remove_yaml_block_markers` |
| Role `.yml` files | `keycloak_runtime/defaults/main.yml`, `tasks/main.yml` | `_remove_role_inline_markers` (calls both handlers) |

### 3. Commission Integration

`scaffold_service.py` adds matching scaffolded blocks wrapped in markers when commissioning a new service:

- `update_platform_services_registry()` — appends a marker-wrapped block to `platform_services.yml`
- `update_keycloak_role_defaults()` — appends a marker-wrapped variable stub to `keycloak_runtime/defaults/main.yml` (when `--oidc` is requested)
- `print_checklist()` — reminds the operator to manually add task blocks to `keycloak_runtime/tasks/main.yml`

### 4. Test Function Removal

`decommission_service.py` uses the Python AST module (`_remove_service_test_functions`) to
surgically remove test functions whose names contain any service variant from `tests/test_*.py` files.
This eliminates the need for manual grep-and-delete of residual test code.

### 5. Monitors Integration

`config/uptime-kuma/monitors.json` entries now carry a `service_id` field.
The CATALOG_REGISTRY entry (`json_array_flat` type) uses this field to remove the corresponding
uptime monitor atomically when a service is decommissioned.

---

## Consequences

**Positive:**
- Commission and decommission are symmetric: `scaffold_service.py` writes markers; `decommission_service.py` removes them.
- The `--validate-registry` flag on `decommission_service.py` catches missing blocks before any mutation.
- `keycloak_runtime` shared role is now safe to decommission from (Gap 3 closed).
- `platform_services.yml` orphaned-body gap closed (Gap 2 closed).
- Test residue cleaned automatically (Gap 6 closed).
- Uptime Kuma monitors cleaned automatically (Gap 7 closed).

**Negative / Trade-offs:**
- `keycloak_runtime/tasks/main.yml` task blocks must still be manually authored — the scaffold cannot
  generate valid Jinja2/module task syntax without service-specific knowledge.
- The marker comment format is YAML-valid (comments are ignored by parsers) but must not be
  renamed or reformatted without updating both migration scripts and the regex in
  `_remove_yaml_block_markers`.

---

## Migration

Three one-time migration scripts were written and run:

1. `scripts/migrate_platform_services_markers.py` — added markers to all 70 service blocks in `platform_services.yml`
2. `scripts/migrate_keycloak_markers.py` — added markers to keycloak defaults (38 marker pairs) and tasks (72 marker pairs)
3. `scripts/migrate_monitors_service_ids.py` — added `service_id` field to 39 of 47 monitors

---

## Related

- ADR 0396 — Deterministic Service Decommissioning Procedure
- ADR 0402 — JupyterHub Removal (postmortem with 7 gaps)
- `docs/postmortems/adr-0402-jupyterhub-removal-2026-04-10.md` — full gap analysis
