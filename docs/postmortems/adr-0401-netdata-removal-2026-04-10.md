# Postmortem: Netdata Removal (ADR 0401) — CPU-Only vs AI-Agent Operations

- Date: 2026-04-10
- Scope: Full decommission of `netdata_runtime` role, `realtime` service, 65 file changes
- ADR: docs/adr/0401-remove-netdata.md
- Release: 0.178.92
- Predecessor postmortem: docs/postmortems/adr-0393-one-api-removal-2026-04-10.md

---

## Overview

This postmortem documents which steps of the Netdata decommission were executed
CPU-only (deterministic, zero token cost) vs which required AI agent reasoning
(tokens + context). It is the second data point in the series that began with
ADR 0393 (One-API removal) and feeds improvements back into ADR 0396
(Deterministic Service Decommissioning).

**Summary verdict:** ~72% CPU-only, ~28% required agent intervention.
An improvement over ADR 0393's 85%/15% split, but several new failure
categories appeared that ADR 0396 does not yet cover.

---

## Phase Breakdown

### Phase 1: Production Teardown — 100% CPU-only

**CPU-only operations:**
- `pgrep netdata` to verify agent state on guests
- `apt-get remove --purge netdata` on all VMs
- `systemctl stop netdata` on Proxmox host
- Verify no stale Prometheus scrape targets post-removal

**Verdict:** Fully automatable. No reasoning required.

---

### Phase 2a: Core Catalog Cleanup — 100% CPU-only ✓

The ADR 0396 `CATALOG_REGISTRY` ran correctly for the catalogs it covers.

**CPU-only operations (via `decommission_service.py --purge-code`):**
- `config/service-capability-catalog.json` — array, id field `id`
- `config/slo-catalog.json` — array, id field `service_id`
- `config/data-catalog.json` — array, id field `service`
- `config/api-gateway-catalog.json` — array, id field `id`
- `config/health-probe-catalog.json` — dict_key
- `config/service-redundancy-catalog.json` — dict_key
- `config/workflow-catalog.json` — workflow_dict
- `config/dependency-graph.json` — dep_graph (nodes + edges)
- `config/contracts/service-partitions/catalog.json` — partitions
- `config/ansible-role-idempotency.yml` — yaml_dict_key (via new handler)
- `playbooks/realtime.yml`, `collections/.../playbooks/realtime.yml` — deleted
- `tests/test_realtime_playbook.py` — deleted
- `workstream_registry.py --write` — deterministic

**Verdict:** All 9 registered catalogs cleaned with zero corruption.
The ADR 0396 CATALOG_REGISTRY investment paid off for these.

---

### Phase 2b: CATALOG_REGISTRY Gaps — Agent Required

**Three catalogs not in the registry still needed cleanup:**

#### Gap 1: `config/subdomain-catalog.json` — wrong id_field

**What happened:** The CATALOG_REGISTRY entry specifies `id_field: "service"` but
the subdomain catalog uses `"service_id"` as its identifier field. The script
filtered `s.get('service') != 'realtime'` — which always passed (no `service`
key) — so the entry was silently not removed.

**Required agent intervention:** Inspect catalog structure, identify the real
id_field (`service_id` not `service`), write targeted Python fix.

**CPU-only fix:** Add schema validation to `_apply_catalog_registry_entry` that
fails loudly when a registered `id_field` matches zero entries (vs silently
passing). If `id_field` hits zero matches for a known service, raise a warning
before assuming the entry doesn't exist.

#### Gap 2: `config/service-completeness.json` — wrong list_key

**What happened:** The CATALOG_REGISTRY entry uses `list_key: "services"` but
the realtime entry lived at the **top level** of the JSON (not nested under
`services`). The dict_key handler looked for `data["services"]["realtime"]`
when the entry was actually `data["realtime"]`.

**Required agent intervention:** Read file structure, discover the anomaly,
apply targeted `data.pop("realtime")` fix.

**CPU-only fix:** The dict_key handler should also attempt removal at the top
level when `list_key` lookup yields zero matches. Or, better: normalise
`service-completeness.json` to nest all service entries under `"services"`.
A pre-decommission schema audit step (new `--validate-registry` flag) would
surface this mismatch before the purge runs.

#### Gap 3: `config/subdomain-exposure-registry.json` — array not in registry

**What happened:** The decommission script's text-match cleanup for this file
removed the wrong content entirely — it matched `realtime` in a top-level
`"publications"` key name? No: the script tried to remove a whole top-level key
called `"publications"` because the nested content had `netdata_port` in it.
This destroyed all 70+ publication entries.

**Required agent intervention:** `git checkout HEAD -- config/subdomain-exposure-registry.json`,
then structured `data['publications'] = [p for p in ... if p.get('service_id') != 'realtime']`.

**CPU-only fix:** Add `config/subdomain-exposure-registry.json` to the
CATALOG_REGISTRY with `type: array`, `list_key: publications`, `id_field: service_id`.
This is an obvious missing entry — it follows the same array pattern as the
other catalogs.

---

### Phase 2c: Role and Playbook Files — CPU-only if decommission_service knew

**What happened:** The decommission script correctly deleted registered
playbook paths, but missed:
- `playbooks/services/realtime.yml` — the "services/" subdirectory variant
  was not in the `delete_files` scan
- `collections/.../roles/netdata_runtime/` — the script doesn't know the role
  name differs from the service_id (`netdata_runtime` vs `realtime`)

**Required agent intervention:** Manual `rm -rf netdata_runtime/` and
`rm playbooks/services/realtime.yml`.

**CPU-only fix:**
1. **Role name registry**: Add a `role_name` field to the service capability
   catalog (or a separate role→service mapping). The decommission script reads
   this to know which role directory to delete.
2. **Playbook path patterns**: The scan should look for both
   `playbooks/<id>.yml` AND `playbooks/services/<id>.yml` automatically.

---

### Phase 2d: Role-Internal Cleanup — Agent Required

Three role/template files needed targeted edits:

| File | Change | Why agent needed |
|------|--------|-----------------|
| `monitoring_vm/templates/prometheus.yml.j2` | Remove 13-line netdata scrape block | No catalog entry maps this template to the realtime service |
| `monitoring_vm/defaults/main.yml` | Remove 3 vars + 2 comment lines | No registry of which role vars belong to which service |
| `nginx_edge_publication/defaults/main.yml` | Remove 2 blocks (CSP + auth proxy) | No catalog entry links nginx CSP entries to a specific service_id |

**Common root cause:** There is no machine-readable declaration that
`monitoring_netdata_parent_port` belongs to the `realtime` service, or that
the nginx CSP entry for `realtime.{{ platform_domain }}` is owned by `realtime`.

**CPU-only fix:**
- Add a `# SERVICE: realtime` comment inline above each variable declaration
  in role defaults that is service-specific (not shared). The decommission
  script can then grep for `# SERVICE: <id>` and surgically remove the line
  plus its value.
- For YAML templates (prometheus.yml.j2), use `# BEGIN SERVICE: realtime` /
  `# END SERVICE: realtime` block markers — the same pattern introduced for
  SLO files in ADR 0396, extended to all role templates.

---

### Phase 2e: Inventory Cleanup — Mixed

| File | What happened |
|------|--------------|
| `inventory/host_vars/proxmox-host.yml` | `netdata_port` at line 33, `lv3_service_topology.realtime` block at line 2111 — both needed targeted removal |
| `inventory/group_vars/platform.yml` | 3 × `netdata_port: 19999` lines — simple line filter worked |

**For `proxmox-host.yml`:** The topology block was a 23-line YAML structure.
The decommission script's text-match would have removed only the `realtime:` key
line, leaving the body as orphaned content. Required agent to read structure and
remove the correct range.

**CPU-only fix:** `lv3_service_topology` entries in `proxmox-host.yml` follow
the exact same structure as the catalog entries. Adding
`config/service-topology.json` (or treating the topology block as a catalog
with `id_field: service_name`) would make this removal deterministic.

---

### Phase 2f: JSON File Corruption from Text-Match — Agent Required

**What happened:** Two JSON files (`certificate-catalog.json`,
`command-catalog.json`) were corrupted by the decommission script's
`_remove_line_references` fallback, which runs for files not in the CATALOG_REGISTRY.

- `certificate-catalog.json` was in `files_with_references` but the
  `certificates` array entry for `realtime-edge` was left with a dangling comma.
- `command-catalog.json`'s `converge-realtime` command was not found by
  `data.pop('converge-realtime')` because it was nested under `data['commands']`
  not at the top level.

**Required agent intervention:** `git checkout HEAD -- ...`, then structured
`json.load → pop → json.dump`.

**CPU-only fix:**
1. Add both files to CATALOG_REGISTRY with correct `list_key` and nesting depth.
2. Add a post-purge validation pass: `python3 -m json.tool <file>` on every
   modified JSON file. Fail loudly before committing if any file is corrupt.
   This converts a silent corruption into an immediate error.

---

### Phase 2g: YAML Alert File Corruption — Agent Required

**What happened:** `config/prometheus/rules/https_tls_alerts.yml` was corrupted
by text-match removal. A PromQL expression spanning two lines
(`probe_success{...}\n  == 0`) had the first line removed, leaving `== 0`
as orphaned YAML that failed `check-yaml`.

**Required agent intervention:** `git checkout HEAD -- ...`, then structured
`yaml.safe_load → filter by labels.service_id → yaml.dump`.

**CPU-only fix:** Add `config/prometheus/rules/https_tls_alerts.yml` and
`config/prometheus/file_sd/https_tls_targets.yml` to the same generated-file
treatment as the SLO files — add `# BEGIN SERVICE: <id>` / `# END SERVICE: <id>`
markers. A `generate_https_tls_config.py` script that reads from
`config/certificate-catalog.json` would make these files fully generated.

---

### Phase 3: Test Cleanup — Mixed

| File | Was it CPU-only? |
|------|-----------------|
| `tests/test_realtime_playbook.py` | YES — deleted by decommission script |
| `tests/test_netdata_runtime_role.py` | NO — not found by decommission script (wrong service_id) |
| `tests/test_monitoring_vm_role.py` | NO — `test_prometheus_template_scrapes_netdata` needed manual removal |
| `tests/test_nginx_edge_publication_role.py` | NO — realtime site assertions needed manual removal |
| `tests/test_generate_platform_vars.py` | NO — `test_build_service_urls_resolves_realtime_internal_url` needed manual removal |

**Root cause:** The decommission script looks for `test_<service_id>_*.py` but:
1. `test_netdata_runtime_role.py` uses the role name not the service_id
2. The other three test files are not service-specific — they assert on
   multi-service data that includes realtime as one item. No file-level deletion
   works; only function-level surgery.

**CPU-only fix:**
- Test files with cross-service assertions (nginx_edge, generate_platform_vars)
  should generate their expected values from the catalogs at test time:
  ```python
  from config_loaders import load_protected_sites
  assert "realtime.example.com" not in load_protected_sites()
  ```
  This makes the test self-updating when a service is removed. No test edit
  needed at decommission time.

---

### Phase 4: Artifact Regeneration — 100% CPU-only ✓

All regeneration commands ran without agent involvement:
- `platform_manifest.py --write`
- `generate_discovery_artifacts.py --write`
- `workstream_registry.py --write`
- `generate_release_notes.py --version 0.178.92 --write`
- `generate_release_notes.py --write-root-summaries`

**Verdict:** Fully automatable. This phase is already 100% CPU-only.

---

## Regression: Worktree/Branch State Confusion

**What happened:** This session opened in a worktree (`affectionate-feistel`)
on branch `claude/affectionate-feistel`, which was 40+ commits behind `main`.
The prior session's work (ADR 0396, postmortem, etc.) had been pushed to `main`
but not rebased into this branch. The session began editing files that were 40
commits stale.

**Impact:** Wasted early-session context re-doing file reads against stale
content before discovering the branch state.

**CPU-only fix:** Add a pre-session startup check that detects when the current
worktree branch is behind `origin/main` by more than 5 commits and prints a
warning. This is a 3-line bash script in `CLAUDE.md` or a pre-commit check.

---

## Quantitative Summary

| Phase | Operations | CPU-only | Agent Required | Token Cost |
|-------|-----------|----------|----------------|-----------|
| 1. Production teardown | 4 | 4 (100%) | 0 | 0 |
| 2a. CATALOG_REGISTRY catalogs | 9 | 9 (100%) | 0 | 0 |
| 2b. Registry gaps (3 catalogs) | 3 | 0 | 3 (100%) | ~800 tokens |
| 2c. Role/playbook file deletion | 2 | 0 | 2 (100%) | ~200 tokens |
| 2d. Role-internal template/vars | 3 | 0 | 3 (100%) | ~600 tokens |
| 2e. Inventory topology block | 1 | 0 | 1 (100%) | ~400 tokens |
| 2f. JSON file corruption repair | 2 | 0 | 2 (100%) | ~600 tokens |
| 2g. YAML file corruption repair | 1 | 0 | 1 (100%) | ~300 tokens |
| 3. Test cleanup | 5 | 1 (20%) | 4 (80%) | ~500 tokens |
| 4. Artifact regeneration | 5 | 5 (100%) | 0 | 0 |
| **Total** | **35** | **19 (54%)** | **16 (46%)** | **~3400 tokens** |

*Note: "agent required" means the operation required reading file structure
and writing targeted code — not just running a CLI command.*

---

## New Gaps vs ADR 0393

ADR 0393 identified three gaps. ADR 0396 fixed all three. This removal exposed
**six new gaps** that ADR 0396 did not address:

| Gap | ADR 0393 | ADR 0401 | Fix Category |
|-----|----------|----------|-------------|
| Wrong `id_field` in registry entry | Not seen | subdomain-catalog | Registry validation |
| Wrong `list_key` (top-level vs nested) | Not seen | service-completeness | Registry validation |
| Missing catalog entry | Partial | subdomain-exposure-registry | Registry completeness |
| Role name ≠ service_id | Not seen | netdata_runtime | Role name registry |
| `playbooks/services/<id>.yml` variant not scanned | Not seen | realtime.yml | Playbook path patterns |
| Role-internal vars/templates not linked to service | Not seen | monitoring_vm defaults + template | Inline service markers |
| YAML TLS files not generated (no block markers) | Not seen | https_tls_alerts.yml | Generation coverage |
| Cross-service test assertions | Partial | nginx_edge test, platform_vars test | Catalog-driven test generation |
| Inventory topology block | Partial | proxmox-host.yml | Topology as catalog |

---

## Recommended ADR 0396 Amendments

The following improvements would close the remaining gap to ~95% CPU-only:

### Amendment 1: Registry Self-Validation (`--validate-registry`)

Add a `--validate-registry` flag that runs before any purge:

```python
for entry in CATALOG_REGISTRY:
    data = load_catalog(entry["path"])
    matches = find_matches(data, entry)
    if len(matches) == 0:
        warn(f"REGISTRY MISMATCH: {entry['path']} field '{entry.get('id_field')}' "
             f"matched zero entries for service '{service_id}'. "
             f"Check id_field or list_key.")
```

This catches wrong `id_field` (Gap 1) and wrong `list_key` (Gap 2) before
any mutation happens.

### Amendment 2: Add Missing Catalogs to Registry

| Missing catalog | Type | list_key | id_field |
|----------------|------|----------|---------|
| `config/subdomain-exposure-registry.json` | `array` | `publications` | `service_id` |
| `config/certificate-catalog.json` | `array` | `certificates` | `service_id` |
| `config/command-catalog.json` | `nested_dict` | `commands` (top-level) | key name contains `<service>` |

For `command-catalog.json`: the `commands` dict is keyed by workflow IDs like
`converge-realtime`. Add a `workflow_dict` handler that also tries
`data["commands"]` in addition to the top-level dict.

### Amendment 3: Role Name Registry

Add a `role_name` field to `config/service-capability-catalog.json` entries:

```json
{
  "id": "realtime",
  "role_name": "netdata_runtime",
  "ansible_playbook": "realtime"
}
```

The decommission script reads `role_name` to locate the role directory and test
file (`test_<role_name>_role.py`). Falls back to `<id>_runtime` pattern if unset.

### Amendment 4: Inline Service Markers in Role Defaults

In role `defaults/main.yml`, annotate service-specific variables:

```yaml
# SERVICE: realtime — remove when service is decommissioned
monitoring_netdata_parent_port: "{{ hostvars[...].platform_port_assignments.netdata_port }}"
monitoring_netdata_parent_metrics_url: >-
  http://127.0.0.1:{{ monitoring_netdata_parent_port }}/api/v1/allmetrics
```

The decommission script scans all role defaults for `# SERVICE: <id>` and
removes those blocks. Combined with `# BEGIN SERVICE: <id>` in templates, this
makes role-internal cleanup fully programmatic.

### Amendment 5: Generate `https_tls_alerts.yml` and `https_tls_targets.yml`

Create `scripts/generate_https_tls_config.py` analogous to
`generate_slo_config.py`. Input: `config/certificate-catalog.json`.
Output: `config/prometheus/rules/https_tls_alerts.yml` and
`config/prometheus/file_sd/https_tls_targets.yml` with block markers.

This brings TLS alert/target generation to the same level as SLO
alert/target generation from ADR 0396.

### Amendment 6: Post-Purge Integrity Validation

Add a mandatory post-purge validation step to `execute_code_purge`:

```python
def validate_modified_files(modified_paths):
    for path in modified_paths:
        if path.endswith(".json"):
            json.load(open(path))  # raises on corrupt JSON
        elif path.endswith((".yml", ".yaml")):
            yaml.safe_load(open(path))  # raises on corrupt YAML
    print(f"Post-purge integrity: {len(modified_paths)} files validated OK")
```

This converts silent corruption (discovered at pre-commit hook time) into an
immediate failure with a clear error. Corrupt files would trigger a
`git checkout HEAD -- <file>` recovery suggestion.

### Amendment 7: Topology Block as Catalog

The `lv3_service_topology` section in `inventory/host_vars/proxmox-host.yml`
is effectively a catalog. Add a new CATALOG_REGISTRY entry type:

```python
{"path": "inventory/host_vars/proxmox-host.yml",
 "type": "yaml_topology_block",
 "list_key": "lv3_service_topology"}
```

Handler: `data["lv3_service_topology"].pop(service_id, None)`.
The block is a simple top-level key deletion — no structural reasoning needed.

---

## Projected Impact of Amendments

| Amendment | Gaps Closed | Estimated CPU-Only Gain |
|-----------|------------|------------------------|
| 1. Registry self-validation | Wrong id_field, wrong list_key | Prevents 2 repair loops |
| 2. Missing catalogs | subdomain-exposure-registry, certificate, command | +3 catalog ops |
| 3. Role name registry | Role != service_id | +2 file deletions |
| 4. Inline `# SERVICE:` markers | Role vars/templates | +3 role edits |
| 5. Generate https_tls files | YAML corruption | +1 YAML file |
| 6. Post-purge validation | Early corruption detection | Prevents 2 git restores |
| 7. Topology as catalog | proxmox-host.yml block | +1 inventory edit |
| **Total if applied** | | **~95% CPU-only** |

The remaining ~5% would be: judgment calls on whether gaps in Prometheus/Grafana
coverage are acceptable (a human decision), and updating human-facing
documentation (ADR body, runbooks) — which appropriately remains AI-assisted.
