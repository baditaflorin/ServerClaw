# Postmortem: One-API Removal (ADR 0393) — CPU-Only vs AI-Agent Operations

- Date: 2026-04-10
- Scope: Full decommission of `one_api_runtime` and `one_api_postgres` roles, 85 file references, 4 secrets
- ADR: docs/adr/0393-remove-one-api.md
- Release: 0.178.88

---

## Overview

This postmortem documents which steps of the One-API decommission were executed
CPU-only (deterministic, no token cost) vs which required an AI agent. The goal
is to track progress toward a fully programmatic decommission pipeline.

---

## Phase Breakdown

### Phase 1: Production Teardown — 100% CPU-only

**What happened:** Containers were already stopped from a prior manual operation.
Confirmed by `docker compose ps` returning empty. No active database (One-API
uses bundled SQLite, not a dedicated PostgreSQL instance).

**CPU-only operations:**
- SSH to docker-runtime to verify container state
- Grep to confirm no live traffic in Prometheus
- ADR impact analysis via `platform_ops.py impact one_api` (deterministic)

**Verdict:** Fully automatable. A decommission script could confirm teardown
preconditions without any AI involvement.

---

### Phase 2: Code Purge — Mixed (mostly CPU-only, one agent-required step)

**What happened:** The decommission_service.py script handled most of the work
deterministically, but JSON/YAML catalog cleanup required structured reasoning.

**CPU-only operations (deterministic):**
- `decommission_service.py --purge-code --confirm one_api` — deleted role dirs,
  playbooks, test files, config files, scripts
- `grep -rli -E "one_api|one-api|oneapi"` — zero-reference validation
- `python3 -c "import json; json.load(...)"` — catalog integrity verification
- ADR index regeneration via `generate_adr_index.py --write`

**Agent-required operations:**
- **JSON catalog cleanup**: The decommission script's `_remove_line_references`
  leaves orphan keys and trailing commas in JSON. Structured removal (Python
  `json.load → filter → json.dump`) required reasoning about which keys to drop
  and what adjacent structure to preserve. This was delegated to an AI subagent.

  **Why this needed an agent:** The catalogs use varied structures — some are
  flat dicts, some are lists of objects, some are deeply nested. The agent had
  to understand the schema of each catalog to know which keys to remove without
  corrupting the surrounding structure.

- **YAML block removal**: `slo_alerts.yml`, `slo_rules.yml`, and
  `dependency-graph.yaml` had multi-line blocks (alert rules spanning 15-20
  lines, graph edges) that required pattern-aware removal rather than line
  matching.

**Path to CPU-only:** The decommission script could be extended with:
1. A `--catalog-schema` flag that loads the JSON schema for each catalog and
   uses schema-aware filtering
2. A YAML block marker convention (e.g., `# BEGIN one_api` / `# END one_api`)
   baked into all YAML files at write time, enabling `sed`-level block removal

---

### Phase 3: Regenerate Artifacts — 100% CPU-only

**What happened:** All artifact regeneration was deterministic CLI commands.

**CPU-only operations:**
- `platform_manifest.py --write` — reads source files, generates manifest
- `generate_discovery_artifacts.py --write` — reads inventory, generates YAML
- `generate_adr_index.py --write` — scans docs/adr/, generates index
- `generate_release_notes.py --version ... --write` — reads changelog, writes MD

**Verdict:** Fully automatable. These are all pure data transformation scripts
with no reasoning required.

---

### Phase 4: Reconverge Affected Services — Deferred (not executed this session)

**Target:** `monitoring-stack` (Prometheus rules reload, Grafana dashboard removal)

**Status:** The Prometheus rules files (`slo_alerts.yml`, `slo_rules.yml`,
`slo_targets.yml`) and the Grafana dashboard (`one-api.json`) have been purged
from the repo. The reconvergence will push these changes to the monitoring
stack on next `make converge-monitoring-stack`.

**CPU-only operations (when run):**
- `make converge-monitoring-stack env=production`
- Verify rules loaded: `curl -s http://prometheus:9090/api/v1/rules`

**Verdict:** Fully automatable with Ansible. No agent required.

---

### Phase 5: Validation — 100% CPU-only

**What happened:**
```bash
grep -rli --include="*.yml" ... -E "one.api|one_api|oneapi" \
  collections/ inventory/ config/ scripts/ tests/
# Result: empty (zero matches)

python3 -c "import json; json.load(open(f)); print('OK')" # all catalogs
python3 -c "import yaml; yaml.safe_load(open(f))" # all YAML files
```

**Verdict:** Fully automatable. These checks are in the ADR's validation section
and could be a CI step.

---

### Phase 6: Release — 100% CPU-only

**What happened:**
- `echo "0.178.88" > VERSION`
- Edit `changelog.md` (one bullet)
- `generate_release_notes.py --version 0.178.88 --write`
- `generate_release_notes.py --write-root-summaries`
- `platform_manifest.py --write` (version bump)
- `git add ... && git commit ...`
- `git push origin main`

**Verdict:** Fully automatable. The version bump, changelog entry, and release
note generation are all scripted. Only the changelog bullet text required
authoring — a one-line summary that could be templated from the ADR title.

---

## Summary: CPU-Only vs Agent-Required

| Phase | CPU-Only | Agent-Required | Notes |
|-------|----------|----------------|-------|
| 1. Teardown | ✅ | — | Containers already stopped |
| 2a. File deletion | ✅ | — | `decommission_service.py` handles this |
| 2b. JSON catalog cleanup | ⚠️ | ✅ | Schema-aware structured removal |
| 2c. YAML block cleanup | ⚠️ | ✅ | Pattern-aware multi-line block removal |
| 3. Artifact regeneration | ✅ | — | All deterministic scripts |
| 4. Reconvergence | ✅ | — | `make converge-monitoring-stack` |
| 5. Validation | ✅ | — | grep + json.load + yaml.safe_load |
| 6. Release | ✅ | — | Scripted version bump + release notes |

**Overall: ~85% CPU-only. The 15% requiring agent involvement is concentrated
in structured catalog cleanup (Phase 2b/2c).**

---

## Lessons and Improvements

### Lesson 1: Line-level removal is fundamentally wrong for JSON/YAML

The decommission script's `_remove_line_references` corrupted every JSON file
it touched by leaving orphaned keys, trailing commas, and broken nesting.

**Fix already applied:** The script was updated to use structured
`json.load/filter/dump` for JSON files and block markers for YAML. But this
needs a catalog schema registry to be truly automated.

**Recommended next step:** Add a `service_id` field to every catalog entry at
write time. Removal then becomes:
```python
catalog = [e for e in catalog if e.get("service_id") != service_name]
```
This is 100% CPU-only and correct by construction.

### Lesson 2: Binary files in `__pycache__` break text-mode iteration

The decommission script failed with `UnicodeDecodeError` when it hit `.pyc`
files. **Fixed:** Added `__pycache__` to `exclude_dirs` and
`try/except UnicodeDecodeError` in the text processing functions.

### Lesson 3: ADR deprecation regex was brittle

The deprecation step used `**Status:** Accepted` (bold markdown) as the match
pattern, but newer ADRs use `- Status: Accepted` (list item). **Fixed:** The
deprecation sed command now handles both formats.

### Lesson 4: `decommission_service.py --dry-run` output is trustworthy for file
deletion, not for catalog edits

The dry-run accurately predicted which files to delete. It did not accurately
preview the result of line-level catalog edits. **Recommended:** Dry-run should
show structured diffs for catalog edits, not just "would remove N references."

---

## The Vision: Fully CPU-Only Decommission

To reach 100% CPU-only decommissioning, the remaining gaps are:

1. **Catalog schema registry**: Map each catalog file to its schema and the
   field name used as service identifier (e.g., `"id"`, `"service_id"`,
   `"name"`). The decommission script loads the schema, identifies the key, and
   filters. No AI needed.

2. **YAML block markers**: When roles write YAML entries (slo rules, alert
   rules, targets), wrap them in:
   ```yaml
   # BEGIN SERVICE: one_api
   ...
   # END SERVICE: one_api
   ```
   Removal becomes a single `sed` command. Block markers should be generated by
   the Ansible role templates at deployment time.

3. **Pre-computed impact graph**: `platform_ops.py impact <service>` already
   generates the dependency graph. A decommission dry-run could fully enumerate
   all downstream effects before any file is touched.

With these three improvements, a full service decommission would be:
```bash
python3 scripts/decommission_service.py --service one_api \
  --purge-code --confirm one_api \
  --structured-catalog-cleanup \
  --yaml-block-markers
# Then:
make converge-monitoring-stack env=production
python3 scripts/platform_manifest.py --write
python3 scripts/generate_release_notes.py --version X.Y.Z --write
git add ... && git commit && git push
```

**Zero AI tokens required.**
