# ADR 0392 — Optional Secret Propagation in Role Convergence

| Field | Value |
|---|---|
| **Status** | Implemented |
| **Date** | 2026-04-10 |
| **Concerns** | convergence reliability, secret management, DRY |
| **Supersedes** | — |
| **Depends on** | ADR 0370 (check_local_secrets), ADR 0373 (service registry pattern) |

## Context

Several roles hard-fail during convergence when optional secret files are
missing on the controller, even though the features those secrets enable
are themselves optional.  Example: `windmill_runtime` fails if
`.local/openbao/atlas-approle.json` is absent, even though that file is
only consumed by the Atlas drift-check scheduled job and the environment
variable injection already uses `errors='ignore'`.

This creates a circular dependency problem:

1. OpenBao convergence creates `atlas-approle.json`.
2. Windmill convergence mirrors that file to the worker checkout.
3. But if OpenBao hasn't been converged yet (or the approle expired),
   Windmill convergence is completely blocked — even for unrelated changes
   like deploying a new workflow script.

The same pattern affects any role that mirrors secrets from roles that
may not yet be converged (new forks, disaster recovery, incremental
bootstrapping).

## Decision

### 1. Add `optional: true` flag to secret file declarations

Both `check_local_secrets` (shared preflight) and per-role secret file
lists now support an `optional` key:

```yaml
# In check_local_secrets callers:
common_check_local_secrets_files:
  - path: "{{ proxmox_api_token_local_file }}"
    description: "Proxmox API token payload"
    prerequisite: "Converge proxmox_api_access to enable the reaper"
    optional: true

# In secret mirror lists:
windmill_worker_repo_secret_files:
  - path: "{{ ... }}/atlas-approle.json"
    src: "{{ ... }}/atlas-approle.json"
    mode: "0600"
    optional: true
```

### 2. Shared task behaviour

`common/tasks/check_local_secrets.yml` now:

- **Required secrets** (`optional` absent or `false`): hard-fail with
  actionable message (unchanged behaviour).
- **Optional secrets** (`optional: true`): emit a debug warning and
  continue.  The feature that depends on the secret will be unavailable
  until the prerequisite is converged.

### 3. Mirror task behaviour

Secret mirror tasks (`ansible.builtin.copy` loops) now:

1. Stat optional files on the controller first.
2. Build the copy loop from required files + optional files that exist.
3. Missing optional files are silently skipped.

This is a data-driven pattern: the defaults declare which secrets are
optional, and the tasks respect that flag — no per-secret conditionals
scattered through task files.

## Consequences

- **Windmill converges without OpenBao approle**: The atlas-approle is
  mirrored when available, skipped when not.  The Atlas drift-check job
  will fail at runtime if the approle is missing, but all other Windmill
  functionality works.
- **Incremental bootstrap**: New forks can converge services in any order
  without hitting missing-secret deadlocks.
- **Existing behaviour preserved**: All currently required secrets remain
  required.  Only secrets explicitly marked `optional: true` get the
  soft-fail treatment.
- **Single pattern**: Any role can use `optional: true` in both
  `check_local_secrets` and secret mirror lists without custom task logic.

## Files

| File | Action |
|---|---|
| `roles/common/tasks/check_local_secrets.yml` | Modified — skip optional, warn |
| `roles/windmill_runtime/defaults/main.yml` | Modified — `optional: true` on approle entries |
| `roles/windmill_runtime/tasks/main.yml` | Modified — stat+filter pattern for optional mirrors |
