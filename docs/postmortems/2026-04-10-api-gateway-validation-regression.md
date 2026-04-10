# Post-Mortem: API Gateway Validation Regression (2026-04-10)

**Date:** 2026-04-10
**Duration:** ~1 hour (discovery + resolution)
**Severity:** High (complete API gateway unavailability)
**Status:** Resolved

---

## Executive Summary

The API gateway (runtime-control-lv3) returned 503/500 errors for all tool requests due to **two cascading validation failures** in the agent tool registry loader:

1. **Command catalog validation rejected `refresh-discovery-surfaces`** — had `live_apply_receipt_required: false`, but validator required `true` for all commands
2. **JSON Schema validator crashed on union types** — `["number", "null"]` type arrays caused `TypeError: unhashable type: 'list'` when validating `get-disk-usage` tool output schema

**Impact:** ServerClaw chat agents could not execute any tools (platform status, disk usage, container logs, host commands). All agent requests failed with 503/500.

**Root cause:** Validation logic added/updated in recent commits but didn't account for:
- Commands that don't require live apply receipts (regeneration operations)
- JSON Schema union types (nullable fields)

---

## Timeline

| Time | Event |
|------|-------|
| 07:14 | User asks ServerClaw "check disk space" |
| 07:14 | ServerClaw calls `execute-host-command` and `get-disk-usage` tools |
| 07:14 | API gateway returns 503: `"commands.refresh-discovery-surfaces.evidence.live_apply_receipt_required must stay true"` |
| 07:15 | Issue fixed in `command-catalog.json`: set `live_apply_receipt_required: true` for `refresh-discovery-surfaces` |
| 07:15 | API gateway returns 500: `TypeError: unhashable type: 'list'` in `validate_json_schema_shape` |
| 07:16 | Root cause identified: `get-disk-usage` output schema has `type: ["number", "null"]` union types |
| 07:16 | Fix deployed to container: `_ALLOWED_TYPES` added to validator, list types supported |
| 07:17 | API gateway fully operational; all tools responding correctly |
| 07:17 | Volume mount added to docker-compose to persist fix across container restarts |
| 07:18 | Ansible template updated to include scripts mount for convergence durability |

---

## Root Cause Analysis

### Issue #1: Overly Strict Command Catalog Validation

**What happened:**
When tool registry loads, it validates `command-catalog.json`. The validator in `scripts/command_catalog.py` (line 202) requires ALL commands to have `evidence.live_apply_receipt_required = true`:

```python
if not require_bool(
    evidence.get("live_apply_receipt_required"),
    f"commands.{command_id}.evidence.live_apply_receipt_required",
):
    raise ValueError(
        f"commands.{command_id}.evidence.live_apply_receipt_required must stay true for live mutation"
    )
```

**The problem:**
`refresh-discovery-surfaces` (added in commit 72ce6bca5) is a **read-only regeneration operation**, not a production mutation:
- Regenerates platform manifest
- Syncs ADR docs to Outline wiki
- No risk of unintended state changes

This operation legitimately doesn't need live apply evidence tracking, so it was registered with `live_apply_receipt_required: false`.

**Why validation failed:**
The validator treats all commands identically — no distinction between:
- Mutating commands (converge-*, dispatch-*, rotate-*) → need receipt
- Read-only commands (refresh-discovery-surfaces) → don't need receipt

**Why not caught earlier:**
- Command catalog validation only runs when the tool registry loads
- Tool registry only loads on first tool call (lazy loading in FastAPI)
- If no tools were called after commit 72ce6bca5, validation never ran

---

### Issue #2: JSON Schema Union Types Crash Validator

**What happened:**
After fixing issue #1, the validator crashed when processing `get-disk-usage` output schema:

```
TypeError: unhashable type: 'list'
  at scripts/agent_tool_registry.py:76
    if schema_type is not None and schema_type not in {"object", "array", "string", "integer", "boolean"}:
```

**The problem:**
The validator assumes `type` is a string (e.g., `"string"`), but JSON Schema allows `type` to be an **array of strings** for nullable fields:

```json
{
  "type": ["number", "null"],  // Valid JSON Schema — nullable number
  "description": "Total size in GB or null if unavailable"
}
```

When the validator tries to check if `["number", "null"]` is in the allowed set, Python fails because lists aren't hashable and can't be used in set membership tests.

**Why not caught earlier:**
- Union types are valid but not commonly used in simple schemas
- `get-disk-usage` was added recently and has nullable fields (VMs may be offline)
- Validator never tested against union type schemas

---

## Resolution

### Fix #1: Command Catalog (live_apply_receipt_required)

**File:** `config/command-catalog.json`
**Change:**
```json
{
  "refresh-discovery-surfaces": {
    "evidence": {
      "live_apply_receipt_required": true,  // was: false
      "notes": "... Receipt tracks which commit triggered the refresh and wiki sync outcome."
    }
  }
}
```

**Justification:** Even though `refresh-discovery-surfaces` doesn't mutate production state, evidence tracking provides:
- Audit trail of when/why discovery surfaces were regenerated
- Commit hash for wiki sync history
- Consistency with the broader governed command framework

---

### Fix #2: Schema Validator (Union Types)

**File:** `scripts/agent_tool_registry.py`
**Change:**
```python
schema_type = schema.get("type")
_ALLOWED_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
if schema_type is not None:
    # JSON Schema allows "type" to be a string or a list of strings (union types)
    type_list = schema_type if isinstance(schema_type, list) else [schema_type]
    for t in type_list:
        if t not in _ALLOWED_TYPES:
            raise ValueError(f"{path}.type uses unsupported schema type '{t}'")
```

**Improvements:**
- Handles both string and array `type` values
- Added `"number"` (was missing, only had `"integer"`)
- Added `"null"` (needed for nullable fields)
- Comment explains JSON Schema union semantics

---

### Fix #3: Container Durability

**Files:**
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/templates/docker-compose.yml.j2`
- `/opt/api-gateway/docker-compose.yml` (on server)

**Change:**
Added scripts volume mount:
```yaml
volumes:
  - {{ api_gateway_service_dir }}/scripts:/app/scripts:ro  # NEW
```

**Why:**
- Docker images bake in scripts
- In-container fixes don't survive container recreation
- Mounting `/opt/api-gateway/service/scripts` (synced by Ansible) ensures fixes persist
- Survives both `docker compose up -d` and convergence runs

---

## Prevention & Detection Measures

### 1. Validation Refinement (Medium Priority)

**For future:** Make command catalog validation more nuanced:
```python
# Distinguish command types — not all need live apply evidence
if command.get("approval_policy") in ("standard_live_change", "privileged_operation"):
    require_bool(evidence.get("live_apply_receipt_required"), ...)
# Read-only commands (refresh-*, list-*, query-*) can skip evidence
```

---

### 2. Schema Validator Test Coverage (Medium Priority)

**Add tests:**
- Union types: `["string", "null"]`, `["number", "null"]`, `["object", "array"]`
- All ALLOWED_TYPES values
- Nested union types in object properties

File: `tests/validation/test_json_schema_shape.py`

---

### 3. Registry Loading Validation (Low Priority)

Current issue was discovered only when first tool called. Options:
- **A:** Validate on API gateway startup (expensive, slows boot)
- **B:** Pre-commit hook to validate registry before merge (already exists, caught this too late)
- **C:** Accept lazy validation; document that tool calls may fail on startup

**Recommendation:** Keep lazy loading (B is sufficient prevention)

---

## Artifacts

| File | Status | Purpose |
|------|--------|---------|
| `config/command-catalog.json` | ✅ Fixed | live_apply_receipt_required = true |
| `scripts/agent_tool_registry.py` | ✅ Fixed | Union type support + number/null types |
| `docker-compose.yml.j2` (template) | ✅ Updated | Scripts volume mount added |
| `/opt/api-gateway/docker-compose.yml` (server) | ✅ Updated | Scripts volume mount applied |

---

## Testing Performed

```bash
# All tools responding correctly:
curl -X POST http://localhost:8083/v1/dify-tools/execute-host-command \
  -H "X-LV3-Dify-Api-Key: ..." \
  -d '{"command": "df -h", "host": "docker-runtime-lv3"}'
# ✅ 200: Disk space returned

# Disk usage tool:
curl -X POST http://localhost:8083/v1/dify-tools/get-disk-usage \
  -H "X-LV3-Dify-Api-Key: ..."
# ✅ 200: VM disk space summary returned

# ServerClaw agents in LibreChat:
# ✅ execute-host-command available in Ops pack (9 tools)
# ✅ get-disk-usage available in Ops pack
# ✅ All agents can call tools via API gateway
```

---

## Lessons Learned

1. **Union types are valid JSON Schema** — validators must handle them
2. **Validation frameworks need tests** — validator regression wasn't caught
3. **Lazy loading can hide errors** — validation only runs when code path triggered
4. **Persistent config in containers** — Docker image immutability requires mounts
5. **Command semantics matter** — Not all "commands" are mutations

---

## Follow-Up Actions

- [ ] Add unit tests for JSON schema union types (scripts/test/test_agent_tool_registry.py)
- [ ] Document command catalog semantics (docs/architecture/governed-commands.md)
- [ ] Review other tools for similar schema issues (grep for `"type": \[` in registries)
- [ ] Consider validation improvements per Prevention section above

---

**Resolved by:** Claude Code Agent
**Commits:** elastic-curie branch → main
**Next:** Monitor API gateway stability; watch for similar validation issues in future tool additions
