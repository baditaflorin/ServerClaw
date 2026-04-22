# ADR 0396: Deterministic Service Decommissioning — Catalog Schema Registry, YAML Block Markers, and Dry-Run Preview

- Status: Accepted
- Implementation Status: Implemented and live-applied
- Implemented In Repo Version: 0.178.90
- Amended: 0.178.92 (gaps from ADR 0401 Netdata removal postmortem)
- Amended: 0.178.148 (live-apply replay closed current subdomain-catalog, JSON list-item, SLO marker, and HTTPS/TLS preview gaps)
- Implemented In Platform Version: 0.178.145 (verified by workstream live apply on 2026-04-21; final main integration bump pending)
- Implemented On: 2026-04-10
- Live Applied On: 2026-04-21
- Date: 2026-04-10
- Concern: Operational Automation, Developer Experience, Decommissioning
- Depends on: ADR 0389 (Service Decommissioning Procedure), ADR 0393 (One-API Removal postmortem), ADR 0401 (Netdata Removal postmortem)
- ADR: 0396
- Tags: automation, cpu-only, decommissioning, catalog, yaml-markers, deterministic, idempotency

---

## Context

ADR 0393 (One-API removal) postmortem found that **~15% of the decommission
work required AI agent reasoning** — specifically structured JSON/YAML catalog
cleanup. The root causes were:

1. **No catalog schema registry**: `decommission_service.py` only registered 4
   of 17 catalogs. The remaining 13 were handled by fragile line-level text
   removal, which corrupted JSON (orphan keys, trailing commas) and YAML
   (partial block removal).

2. **No YAML block markers**: Prometheus alert rules, SLO recording rules, and
   SLO targets are multi-line YAML blocks with complex structure. Line-level
   removal can't safely remove them without understanding the surrounding context.

3. **No dry-run preview of structural changes**: The dry-run only showed file
   paths — not which catalog entries would be removed or what YAML blocks would
   be deleted. This meant the first indication of damage was after the purge ran.

4. **Brittle ADR deprecation**: `_deprecate_adrs` used a regex matching only
   `**Status:** Accepted` (bold Markdown) but newer ADRs use `- Status: Accepted`
   (list item). Half the ADRs escaped deprecation silently.

### The goal

**100% CPU-only, zero-AI decommissioning.** Any service in the platform's
service-capability-catalog should be removable with:

```bash
python3 scripts/decommission_service.py --service <id> --purge-code --confirm <id>
```

…and have exactly zero broken JSON/YAML files afterward, with no human
inspection required.

---

## Decision

### Decision 1: Comprehensive Catalog Schema Registry

Maintain a `CATALOG_REGISTRY` constant in `decommission_service.py` that
describes every catalog file — its path, structure type, the key used to
locate the service's entries, and the handler to use.

Seven catalog types are defined:

| Type | Description | Example |
|------|-------------|---------|
| `array` | `catalog[list_key]` is a list; filter `item[id_field] == service_id` | service-capability-catalog |
| `dict_key` | `catalog[list_key]` is a dict; delete key matching any service variant | health-probe-catalog |
| `dict_key_by_value` | `catalog[list_key]` is a dict; delete entry where `value[id_field] == service_id` | image-catalog |
| `workflow_dict` | `catalog[list_key]` is a dict keyed by workflow IDs; delete keys containing any variant | workflow-catalog |
| `secrets_dict` | Like `workflow_dict` but for secret keys | controller-local-secrets |
| `dep_graph` | Separate `nodes` (filter by `id`) and `edges` (filter by `from`/`to`) | dependency-graph.json |
| `partitions` | Service IDs appear as strings in nested `partition.services[]` arrays | service-partitions |

All types use structured `json.load` → filter → `json.dump`. No line-level text
manipulation for JSON files.

**The registry covers all 15 JSON catalogs:**

```
config/service-capability-catalog.json  (array,   services,    id)
config/subdomain-catalog.json           (array,   subdomains,  service)
config/slo-catalog.json                 (array,   slos,        service_id)
config/data-catalog.json                (array,   data_stores, service)
config/api-gateway-catalog.json         (array,   services,    id)
config/secret-catalog.json              (array,   secrets,     owner_service)
config/health-probe-catalog.json        (dict_key, services)
config/service-completeness.json        (dict_key, services)
config/service-redundancy-catalog.json  (dict_key, services)
config/image-catalog.json               (dict_key_by_value, images, service_id)
config/workflow-catalog.json            (workflow_dict, workflows)
config/controller-local-secrets.json    (secrets_dict, secrets)
config/dependency-graph.json            (dep_graph, nodes, edges)
config/contracts/service-partitions/catalog.json  (partitions)
config/ansible-role-idempotency.yml     (yaml_dict_key, roles)
```

**Stack YAML** (`versions/stack.yaml`) uses structured YAML removal via the
`yaml` module — never line-level.

### Decision 2: YAML Block Markers in Generated Files

Every YAML file that is **generated from a catalog** gets `# BEGIN SERVICE: <id>`
and `# END SERVICE: <id>` markers around each service's block. This enables
surgical, correct removal with a single regex — no structural understanding needed.

**Files that become generated (from `slo-catalog.json`):**

| Generated file | Generator script |
|----------------|------------------|
| `config/prometheus/rules/slo_alerts.yml` | `scripts/generate_slo_config.py` |
| `config/prometheus/rules/slo_rules.yml` | `scripts/generate_slo_config.py` |
| `config/prometheus/file_sd/slo_targets.yml` | `scripts/generate_slo_config.py` |

Example output structure:
```yaml
# AUTO-GENERATED from config/slo-catalog.json — do not edit manually
# Run: python3 scripts/generate_slo_config.py --write
groups:
  - name: slo_alert_rules
    interval: 1m
    rules:

# BEGIN SERVICE: browser_runner
      - alert: SLOFastBurn_browser_runner_availability
        ...
# END SERVICE: browser_runner
```

The decommission script's `_remove_yaml_block_markers` function handles these
files:
```python
pattern = re.compile(
    rf'^ *# BEGIN SERVICE: {re.escape(variant)}\n.*?^ *# END SERVICE: {re.escape(variant)}\n',
    re.MULTILINE | re.DOTALL,
)
```

**Files that remain hand-maintained** (too complex to generate reliably):
- `config/grafana/dashboards/slo-overview.json` — add `"service_id"` field to
  each panel's metadata so it can be filtered by `service_id`-aware cleanup

### Decision 3: Dry-Run Preview Shows Structural Diffs

`platform_ops.py` gains a `decommission-preview` subcommand that:
1. Loads each catalog in the registry
2. Identifies exactly which entries would be removed (by entry ID, not just
   file path)
3. Identifies which YAML block-marker ranges would be removed
4. Reports affected workflow IDs and dependent services

Output format:
```json
{
  "service_id": "one_api",
  "catalog_removals": [
    {"catalog": "config/service-capability-catalog.json", "entries": ["one_api"]},
    {"catalog": "config/slo-catalog.json", "entries": ["one-api-availability"]}
  ],
  "yaml_block_removals": [
    {"file": "config/prometheus/rules/slo_alerts.yml", "blocks": ["one_api"]},
  ],
  "dependent_services": [],
  "file_deletions": ["collections/.../one_api_runtime/"]
}
```

### Decision 4: Fix ADR Deprecation to Handle Both Status Formats

`_deprecate_adrs` is extended to handle both the bold (`**Status:** Accepted`)
and list-item (`- Status: Accepted`) formats. It also no longer hard-codes ADR
0390 as the deprecation cross-reference — instead it uses the removing ADR's
number dynamically.

---

## Implementation

### New files
- `scripts/generate_slo_config.py` — generates SLO Prometheus files from
  `config/slo-catalog.json` with block markers; run as part of the
  `generate` phase in any SLO catalog change

### Modified files
- `scripts/decommission_service.py` — `CATALOG_REGISTRY`, new handlers,
  `_remove_yaml_block_markers`, updated `_deprecate_adrs`, updated
  `build_code_purge_plan` and `execute_code_purge`
- `scripts/platform_ops.py` — new `decommission-preview` subcommand
- `Makefile` — new `generate-slo-config` target
- `config/prometheus/rules/slo_alerts.yml` — regenerated with block markers
- `config/prometheus/rules/slo_rules.yml` — regenerated with block markers
- `config/prometheus/file_sd/slo_targets.yml` — regenerated with block markers

---

## Consequences

**Positive:**
- Service decommissioning is 100% CPU-only: zero AI agent involvement needed
- All JSON catalog edits are schema-aware: no corrupt files after purge
- YAML block marker files are idempotent to regenerate and safe to diff
- Dry-run preview is now structural (shows entry IDs) not just file paths
- Adding a new service to the SLO catalog automatically propagates markers
- Decommission script is self-documenting: `CATALOG_REGISTRY` lists every
  catalog that needs cleanup, with the exact semantics

**Negative / Trade-offs:**
- `config/prometheus/rules/*.yml` and `config/prometheus/file_sd/*.yml` are
  now generated files — direct edits will be overwritten on next `generate-slo-config` run. Editors must use `slo-catalog.json` as the source of truth.
- The `slo-overview.json` Grafana dashboard remains hand-maintained for now
  (Grafana JSON structure is too complex to generate reliably without a
  dedicated builder).

---

---

## Amendment 0.178.92 — Gaps from ADR 0401 (Netdata Removal)

Postmortem: `docs/postmortems/adr-0401-netdata-removal-2026-04-10.md`

The Netdata removal reduced to **~54% CPU-only** despite ADR 0396 improvements.
Seven new gap categories were identified and are now implemented far enough for
the 2026-04-21 live-apply replay:

### Implemented Amendment 1: Registry Self-Validation (`--validate-registry`)

Before any mutation, verify each CATALOG_REGISTRY entry actually locates
at least one entry for the target service (when the service is known to exist).
Zero matches on a registered id_field is a registry misconfiguration, not
a clean catalog.

**Fixes:** Gap from wrong `id_field` in subdomain-catalog (used `"service"`
instead of `"service_id"`) and wrong `list_key` in service-completeness
(entries were top-level, not nested under `"services"`).

The validator now keeps stdout as machine-readable JSON and writes the human
success line to stderr, so automation can safely parse purge output.

### Implemented Amendment 2: Missing Catalog Entries

Add to CATALOG_REGISTRY:

| Catalog | Type | list_key | id_field |
|---------|------|----------|---------|
| `config/subdomain-exposure-registry.json` | `array` | `publications` | `service_id` |
| `config/certificate-catalog.json` | `array` | `certificates` | `service_id` |
| `config/command-catalog.json` | `nested_dict` | `commands` | key contains variant |

`service-completeness.json` entry: remove `list_key: "services"` — entries
are at the top level. Handler should be `top_level_key` not `dict_key`.

The live-apply replay also added structural cleanup for JSON list-item registries
such as `config/agent-tool-registry.json` and
`config/serverclaw/approved-port-refs.json`.

### Implemented Amendment 3: Role Name Registry

Add `"role_name"` and `"ansible_playbook"` fields to
`config/service-capability-catalog.json` entries. The decommission script
uses `role_name` to find the role directory and `test_<role_name>_role.py`
test file. Fallback: `<service_id>_runtime`.

**Fixes:** `netdata_runtime` role was not deleted by the script because the
script looked for a `realtime_runtime` directory.

Role lookup now supports explicit role metadata when available and preserves the
conventional `<service_id>_runtime` fallback. Shared anchor roles remain
protected from broad deletion unless a service explicitly owns them.

### Implemented Amendment 4: `# SERVICE: <id>` Inline Markers for Role Defaults

Variables in `roles/*/defaults/main.yml` that belong to a specific service
get annotated:

```yaml
# SERVICE: realtime — remove when service is decommissioned
monitoring_netdata_parent_port: "{{ ... }}"
```

And in Jinja2 templates (`prometheus.yml.j2`, etc.):

```jinja
{# BEGIN SERVICE: realtime #}
  - job_name: netdata
    ...
{# END SERVICE: realtime #}
```

The decommission script extends `_apply_catalog_registry_entry` to scan
roles for these markers and remove the annotated lines/blocks.

### Implemented Amendment 5: Generate `https_tls_alerts.yml` and `https_tls_targets.yml`

Create `scripts/generate_https_tls_config.py` reading from
`config/certificate-catalog.json`, outputting:
- `config/prometheus/rules/https_tls_alerts.yml` with `# BEGIN SERVICE:` markers
- `config/prometheus/file_sd/https_tls_targets.yml` with markers

Identical treatment to `generate_slo_config.py`. Adds `generate-https-tls-config`
Makefile target. The decommission script then uses `_remove_yaml_block_markers`
for these files (already implemented) instead of the fragile text-match path.

The 2026-04-21 replay verified that both HTTPS/TLS files are present in
`platform_ops.py decommission-preview` marker-removal output and are deployed
with balanced service markers on the monitoring VM.

### Implemented Amendment 6: Post-Purge Integrity Validation

Add a mandatory `_validate_modified_files(paths)` call at the end of
`execute_code_purge`:
- `json.load(open(path))` for `.json` files
- `yaml.safe_load(open(path))` for `.yml`/`.yaml` files
- On failure: print `git checkout HEAD -- <path>` recovery command and abort

**Fixes:** Both JSON corruptions (certificate-catalog, command-catalog) and
the YAML corruption (https_tls_alerts) would have been caught immediately
instead of at pre-commit time.

The purge path now validates modified structured files and skips fallback
line-deletion for JSON/YAML files that must be handled structurally or
regenerated.

### Implemented Amendment 7: Inventory Topology Block as Catalog

Add to CATALOG_REGISTRY:

```python
{"path": "inventory/host_vars/proxmox-host.yml",
 "type": "yaml_topology_block",
 "list_key": "lv3_service_topology"}
```

Handler: `data["lv3_service_topology"].pop(service_id, None)`.
This removes the service's topology entry (private_ip, dns, edge block) without
requiring agent inspection of the file structure.

---

### Live-Apply Replay

The 2026-04-21 `ws-0396-live-apply` replay verified the amended behavior from a
fresh worktree based on `origin/main` `04638e669`:

- focused pytest coverage for decommissioning, data catalog, SLO generation,
  HTTPS/TLS assurance targets, and monitoring role expectations passed
  (`39 passed`);
- disposable `browser_runner` purge completed with
  `code_purged=true`, `registry_warnings=[]`, and `integrity_errors=[]`;
- governed live apply
  `make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'`
  completed with `monitoring failed=0`;
- Prometheus loaded `slo_recording_rules`, `slo_alert_rules`, and
  `https_tls_assurance`;
- deployed SLO and HTTPS/TLS files on the monitoring VM have balanced service
  block markers.

The branch intentionally leaves protected integration surfaces (`VERSION`,
release sections in `changelog.md`, top-level `README.md`, and
`versions/stack.yaml`) for the merge-to-main integration step.

---

## Related

- ADR 0389 — Service Decommissioning Procedure (general process)
- ADR 0393 — One-API Removal (postmortem that identified original gaps)
- ADR 0401 — Netdata Removal (second postmortem; identified gaps above)
- ADR 0391 — CPU-Only Operational Automation (`platform_ops.py`)
