# Postmortem: JupyterHub Removal (ADR 0402) — CPU-Only vs AI-Agent Operations

- Date: 2026-04-10
- Scope: Full decommission of `jupyterhub_runtime` role, `jupyterhub` service, ~60 file changes
- ADR: docs/adr/0402-remove-jupyterhub.md
- Release: 0.178.95
- Predecessor postmortem: docs/postmortems/adr-0401-netdata-removal-2026-04-10.md

---

## Overview

This postmortem documents which steps of the JupyterHub decommission were executed
CPU-only (deterministic, zero token cost) vs which required AI agent reasoning
(tokens + context). It is the third data point in the series that began with ADR
0393 (One-API removal) and feeds improvements back into ADR 0396 (Deterministic
Service Decommissioning).

**Summary verdict:** ~60% CPU-only, ~40% required agent intervention.

A regression from the ADR 0401 (Netdata) 72%/28% split. Two root causes:
1. The CATALOG_REGISTRY had a pre-existing type swap bug that was caught by the
   new `--validate-registry` flag (Amendment 1 of ADR 0396) before causing
   corruption — this is a win for Amendment 1, but required agent intervention
   to diagnose and fix the registry itself.
2. Several surfaces that ADR 0396 explicitly identified as "not yet covered"
   (shared role tasks, `platform_services.yml`, non-catalog JSON files) surfaced
   exactly as predicted.

---

## Phase Breakdown

### Phase 1: Pre-Decommission Registry Validation — Agent Required

**What happened:** The new `--validate-registry` flag (ADR 0396 Amendment 1)
was run before the purge. It flagged two CATALOG_REGISTRY entries with zero
matches, indicating a type mismatch:

- `config/service-completeness.json` was registered as `top_level_key` but its
  entries actually live under `.services` (a dict_key with `list_key: services`)
- `config/service-redundancy-catalog.json` was registered as `dict_key/services`
  but its entries live at the root level (top_level_key)

These two entries were swapped. The bug had been in the registry since both
catalogs were added and would have silently skipped removal for both.

**Required agent intervention:** Inspect both files' actual structure, confirm
the swap, fix `CATALOG_REGISTRY` in `scripts/decommission_service.py`.

**CPU-only fix (gap for ADR 0396):** `--validate-registry` correctly surfaced
the problem (Amendment 1 working as designed). The remaining gap: the fix itself
(swapping the types) is a one-line change once the diagnosis is made; a schema
file that declares the canonical type for each catalog could validate this
automatically. Tracked as a future ADR 0396 amendment.

**Note:** This is the first confirmed real-world proof that `--validate-registry`
works. It caught two actual bugs before they caused data corruption. The investment
in Amendment 1 was validated by this decommission.

---

### Phase 2a: Core Catalog Cleanup — 100% CPU-only ✓

After fixing the CATALOG_REGISTRY type swap, the decommission script ran correctly
for all registered catalogs.

**CPU-only operations (via `decommission_service.py --purge-code`):**
- `config/service-capability-catalog.json` — array, id field `id`
- `config/slo-catalog.json` — array, id field `service_id`
- `config/data-catalog.json` — array, id field `service`
- `config/api-gateway-catalog.json` — array, id field `id`
- `config/health-probe-catalog.json` — dict_key
- `config/service-completeness.json` — dict_key, list_key `services` (after fix)
- `config/service-redundancy-catalog.json` — top_level_key (after fix)
- `config/subdomain-exposure-registry.json` — array, list_key `publications`, id_field `service_id`
- `config/workflow-catalog.json` — workflow_dict
- `config/dependency-graph.json` — dep_graph (nodes + edges)
- `config/contracts/service-partitions/catalog.json` — partitions
- `config/ansible-role-idempotency.yml` — yaml_dict_key
- ADR 0291 marked Deprecated — adr_deprecate handler
- Prometheus SLO/TLS block markers removed — yaml_block_markers handler
- `playbooks/jupyterhub.yml`, `playbooks/services/jupyterhub.yml`,
  `collections/.../playbooks/jupyterhub.yml` — deleted
- `tests/test_jupyterhub_playbook.py` — deleted
- `collections/.../roles/jupyterhub_runtime/` — deleted

**Verdict:** All registered surfaces cleaned with zero corruption.

---

### Phase 2b: `platform_services.yml` Orphaned Block — Agent Required

**What happened:** `_remove_line_references` successfully removed the `jupyterhub:`
key line from `inventory/group_vars/all/platform_services.yml`, but left the
entire service configuration body orphaned — 38 lines of `service_type:`,
`internal_port:`, `hairpin:`, `dns:`, `tls:`, `sso:`, `proxy:` config with no
parent key. This is syntactically valid YAML but semantically broken — Ansible
would try to merge these keys into the wrong parent.

**Required agent intervention:** Read the file section, identify the orphaned
block, remove it with Edit tool.

**CPU-only fix (gap for ADR 0396):** `platform_services.yml` uses a large nested
YAML dict format without `# BEGIN SERVICE: jupyterhub` / `# END SERVICE:` block
markers. Adding these markers would allow `_remove_yaml_block_markers` to handle
the entire block atomically. Alternatively: add `platform_services.yml` to
CATALOG_REGISTRY as a new `yaml_service_block` type that strips both the key line
and the indented body block. **This is the highest-priority gap from this decommission.**

---

### Phase 2c: Keycloak Shared Role Tasks — Agent Required

**What happened:** The `keycloak_runtime` role's `tasks/main.yml` contains inline
per-service OIDC client tasks. The decommission script's `_remove_line_references`
handler does not scan shared role task files — it only scans the service's own
role directory. Three distinct JupyterHub task blocks survived:

1. `- name: Ensure the JupyterHub OAuth client exists` — full reconcile block
   (~40 lines) in the large reconcile block list
2. `- name: Read the JupyterHub client secret` — client secret fetch task (11 lines)
3. `keycloak_jupyterhub_client_secret: "..."` — set_fact line in the secret
   materialization task
4. `- name: Mirror the JupyterHub client secret to the control machine` — copy task (8 lines)

Additionally, `keycloak_runtime/defaults/main.yml` had three variable groups:
- `keycloak_jupyterhub_client_id` and `keycloak_jupyterhub_client_secret_local_file`
- `keycloak_jupyterhub_root_url`
- `keycloak_jupyterhub_post_logout_redirect_uris`

**Required agent intervention:** Read both files, identify all blocks, remove
with targeted Edit calls.

**CPU-only fix (gap for ADR 0396):** The decommission script needs a new
`keycloak_shared_role_cleanup` phase that:
1. Scans `keycloak_runtime/tasks/main.yml` for tasks with `name:` containing
   the service name variant
2. Removes matched task blocks (not just lines)
3. Scans `keycloak_runtime/defaults/main.yml` for variables matching the
   `keycloak_<service_id>_*` prefix pattern
This is the second-highest-priority gap.

---

### Phase 2d: Non-Catalog JSON Files — Agent Required

**What happened:** Two JSON files that are NOT in `CATALOG_REGISTRY` contained
JupyterHub references:

1. **`config/workbench-information-architecture.json`** — bookmark with
   `{"title": "JupyterHub", "url": "https://jupyter.example.com"}`. The decommission
   script's text-match pass doesn't parse nested JSON structures.

2. **`config/uptime-kuma/monitors.json`** — monitor entry `{"name": "JupyterHub
   Public Health"}`. Same issue.

**Required agent intervention:** Python inline scripts to load → filter → dump
each file.

**CPU-only fix (gap for ADR 0396):** Add both files to CATALOG_REGISTRY:
- `config/workbench-information-architecture.json` as an `array` type with
  appropriate nested path (the bookmarks are at `sections[*].bookmarks[*]`)
- `config/uptime-kuma/monitors.json` as an `array` type with `id_field: name`
  (monitors use `name` not `id`)

---

### Phase 2e: Port Assignment Outside Topology — Agent Required

**What happened:** `inventory/host_vars/proxmox-host.yml` contains a flat
`jupyterhub_port: 8097` assignment in a port-assignment section that is separate
from the `lv3_service_topology` block (which is covered by the `yaml_topology_block`
handler). The decommission script's topology handler matched the right topology
entry but missed the standalone port variable.

**Required agent intervention:** Read the host_vars file, find the orphaned port
variable, remove it with Edit.

**CPU-only fix (gap for ADR 0396):** The decommission script should scan the
entire host_vars file for variables matching `<service_id>_port:` (and similar
`<service_id>_*` patterns in the flat assignment section) and remove matched lines.

---

### Phase 2f: False Positive in Capability Catalog Notes — Agent Required

**What happened:** `config/service-capability-catalog.json`'s Redpanda entry had
a `notes` field that read: *"...because docker-runtime already reserves 8097
for JupyterHub and 8099 for the Temporal UI."* The decommission script's
text-match pass flagged this as a structural entry to remove, but it was just
a prose comment inside a string value.

**Required agent intervention:** Read the entry, identify it as a comment not a
catalog reference, update the notes string to remove the JupyterHub mention.

**CPU-only fix (gap for ADR 0396):** Text-match cleanup should skip string values
that are `notes`, `description`, or `comment` fields. Or: document that prose
cleanup in string fields is explicitly out of scope for the decommission script.

---

### Phase 2g: Test File Cleanup — Partially CPU-only

The decommission script deleted `tests/test_jupyterhub_playbook.py` (100%
CPU-only via the playbook test deletion handler). Three additional test files
required manual cleanup:

1. **`tests/test_keycloak_runtime_role.py`** — assertions on
   `keycloak_jupyterhub_*` defaults and the retry task name list and the full
   `test_role_manages_jupyterhub_client_secret` test function.

2. **`tests/test_generate_platform_vars.py`** — two test functions:
   `test_build_platform_vars_includes_jupyterhub_publication_topology` and
   `test_build_service_urls_resolves_jupyterhub_internal_url`.

3. **`tests/test_edge_publication_makefile.py`** — one test function:
   `test_converge_jupyterhub_bootstrap_materializes_shared_edge_generated_portals`.

4. **`tests/test_redpanda_playbook.py`** — renamed
   `test_host_network_policy_allows_private_redpanda_ports_without_jupyterhub_collision`
   to drop the jupyterhub reference; removed port 8097 absence assertions.

**Required agent intervention:** Read each file, identify targeted removals,
apply with Edit.

**CPU-only fix (gap for ADR 0396):** A `_remove_service_test_assertions` handler
could scan test files for functions containing the service_id string in the name
and remove them. This would cover most cases. Service-specific assertions inside
shared test functions (like the Keycloak role test) still require reasoning.

---

## Summary Gap Table

| Gap | Severity | CPU-only Fix |
|-----|----------|--------------|
| CATALOG_REGISTRY type swap (validate-registry caught it) | High | Schema file declaring canonical type per catalog |
| `platform_services.yml` orphaned block | High | `# BEGIN/END SERVICE:` markers or new `yaml_service_block` registry type |
| Keycloak shared role tasks/defaults | High | `keycloak_shared_role_cleanup` phase in decommission script |
| Non-catalog JSON files (workbench IA, uptime kuma) | Medium | Add to CATALOG_REGISTRY |
| Port assignment outside topology block | Medium | Scan host_vars for `<service_id>_port:` pattern |
| False positive in notes string | Low | Exclude notes/description fields from text-match |
| Service-specific test assertions | Medium | `_remove_service_test_assertions` handler |

---

## ADR 0396 Amendment Recommendations

Based on this decommission, the following additions to ADR 0396 are recommended:

1. **Amendment: `platform_services.yml` block markers** — Add `# BEGIN SERVICE: <id>` /
   `# END SERVICE: <id>` block markers around every service block, and add
   `platform_services.yml` to CATALOG_REGISTRY as `yaml_service_block`.

2. **Amendment: Keycloak shared role cleanup** — Add a dedicated cleanup phase
   that scans `keycloak_runtime/tasks/main.yml` and `keycloak_runtime/defaults/main.yml`
   for service-specific tasks and variables by name prefix.

3. **Amendment: `--validate-registry` schema file** — Instead of just warning
   on zero matches, have the validator check against a declared canonical
   structure schema for each catalog file. Prevent type mismatches from being
   committed.

4. **Amendment: Uptime Kuma and Workbench IA in CATALOG_REGISTRY** — Add both
   files with appropriate array types and id_fields.

---

## What Went Well

- `--validate-registry` (Amendment 1) caught the CATALOG_REGISTRY type swap
  **before** the purge ran, preventing silent data corruption. This is the most
  important finding: the defensive tooling works.
- All 9 registered catalogs were cleaned correctly in a single invocation after
  the registry fix.
- SLO Prometheus files (slo_alerts.yml, slo_rules.yml, slo_targets.yml) were
  handled automatically by block markers.
- The JupyterHub role and playbooks were fully deleted by the script.
- ADR 0291 was deprecated automatically.
- The decommission overall was cleaner than ADR 0393 (One-API) which had a
  destructive text-match corruption requiring a `git checkout` recovery.
