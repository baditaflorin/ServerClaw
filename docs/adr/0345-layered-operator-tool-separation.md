# ADR 0345: Layered Operator Tool Separation

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.178.4
- Date: 2026-04-04
- Tags: tooling, architecture, dry, separation-of-concerns, contracts, operator-tools

## Context

The `scripts/proxmox_tool.py` tool, introduced to provide zero-SSH guest
operations (ADR 0342), contains both:

1. **Transport primitives** (`guest-exec`, `docker-ps`, `install-key`): Generic
   Proxmox QAPI operations with no knowledge of any specific service.

2. **Application operations** (`coolify-db-exec`, `coolify-clear-cache`,
   `coolify-migrate-apps`, `coolify-install-deploy-key`): Coolify-specific
   database queries, cache management, and app migration logic encoded directly
   in the transport-layer tool.

This mixing creates a layering violation: the Proxmox transport layer now
contains Coolify SQL schema knowledge (`standalone_dockers` table, `destination_id`
column), Coolify container naming conventions (`coolify-db`, `coolify`), and
Coolify cache command semantics (`php artisan cache:clear`).

The same violation will recur if PostgreSQL-specific operations are added to
`proxmox_tool.py`, or if a second application (Woodpecker, Vikunja) needs
similar DB migration support. Each new service would add more application
knowledge to the infrastructure-layer tool.

Additionally, `controller_automation_toolkit.py` (ADR 0039) exists as the
designated home for shared primitives, but neither `coolify_tool.py` nor
`proxmox_tool.py` currently uses it. Both duplicate `load_auth()` and would
duplicate `guest_exec` if the current state is left unchanged.

The `coolify_tool.py` script already owns Coolify API operations. It is the
natural home for Coolify database operations too, since both interact with the
Coolify application layer. Users of `coolify_tool.py` should not need to know
that some Coolify operations go through the REST API and others go through a
Proxmox guest exec path — that routing decision belongs inside the tool.

## Decision

The `scripts/` operator tools are organised into three layers with strict
dependency rules: no layer may import from or shell out to a higher layer.

```
┌───────────────────────────────────────────────────────┐
│  Layer 3: Orchestration (Ansible playbooks)           │
│  Calls Layer 2 tools as ansible.builtin.command       │
│  Never imports Python scripts directly                │
└───────────────┬───────────────────────────────────────┘
                │ (subprocess)
┌───────────────▼───────────────────────────────────────┐
│  Layer 2: Application tools                           │
│  coolify_tool.py, keycloak_tool.py, vikunja_tool.py  │
│  Service-aware: knows API endpoints, DB schema,       │
│  container names, cache commands                      │
│  Imports from Layer 1 (shared toolkit)               │
└───────────────┬───────────────────────────────────────┘
                │ (import)
┌───────────────▼───────────────────────────────────────┐
│  Layer 1: Shared toolkit + transport                  │
│  controller_automation_toolkit.py: load_auth,        │
│  load_topology, guest_exec, JSON output helpers       │
│  proxmox_tool.py: CLI wrapper around QAPI primitives │
│  No service knowledge                                 │
└───────────────────────────────────────────────────────┘
```

### Layer 1 — Shared toolkit and transport primitives

**`controller_automation_toolkit.py`** (shared library, not a CLI tool):
- `load_auth(path) -> dict`
- `load_topology(snapshot_path, env) -> dict`
- `guest_exec(auth, node, vmid, command, timeout=60) -> tuple[int, str, str]`
- `json_output(status, **fields)` — writes JSON to stdout
- `exit_noop(**fields)` — writes no_op JSON and exits 2
- `exit_error(msg, **fields)` — writes error JSON to stderr and exits 1

**`proxmox_tool.py`** (CLI tool, Layer 1):
Generic Proxmox operations. No service knowledge.
Commands: `guest-exec`, `docker-ps`, `install-key`.
Does NOT contain: `coolify-*`, or any command naming a specific service.

### Layer 2 — Application tools

**`coolify_tool.py`** (CLI tool, Layer 2):
All Coolify operations regardless of transport path.
The tool internally decides whether an operation goes via:
- Coolify REST API (`/api/v1/...`), or
- Proxmox QAPI guest exec (via `controller_automation_toolkit.guest_exec`)

This routing is an implementation detail hidden from callers.

Commands to migrate from `proxmox_tool.py` to `coolify_tool.py`:

| Command | Current location | Target location |
|---------|-----------------|-----------------|
| `coolify-db-exec` | `proxmox_tool.py` | `coolify_tool.py` |
| `coolify-clear-cache` | `proxmox_tool.py` | `coolify_tool.py` |
| `coolify-migrate-apps` | `proxmox_tool.py` | `coolify_tool.py` |
| `coolify-install-deploy-key` | `proxmox_tool.py` | `coolify_tool.py` |

After migration, `coolify_tool.py` accepts the same CLI flags as the
current `proxmox_tool.py` subcommands for these operations (backward
compatibility). `proxmox_tool.py` may retain deprecated aliases for one
release cycle with a deprecation warning on stderr.

### Layer 3 — Orchestration

Ansible playbooks call Layer 2 tools via `ansible.builtin.command`.
Playbooks never import Python scripts and never call `proxmox_tool.py`
directly for Coolify-specific operations.

### Dependency rules

| From → To | Allowed? |
|---|---|
| Layer 3 (playbook) → Layer 2 (app tool) via subprocess | ✅ |
| Layer 3 (playbook) → Layer 1 (proxmox_tool) via subprocess | ✅ for generic ops |
| Layer 2 (app tool) → Layer 1 (shared toolkit) via import | ✅ |
| Layer 2 (app tool) → Layer 1 (proxmox_tool) via subprocess | 🚫 |
| Layer 2 (app tool) → Layer 2 (other app tool) via import | 🚫 |
| Layer 1 (shared toolkit) → Layer 2 (app tool) | 🚫 |
| Layer 1 (proxmox_tool) → Layer 1 (shared toolkit) via import | ✅ |

The prohibition on Layer 2 → Layer 1 via subprocess (shelling out to
`proxmox_tool.py`) is because this would bypass the typed `guest_exec`
interface, making mocking in tests impossible and error handling opaque.

## Places That Need to Change

### 1. `scripts/controller_automation_toolkit.py`

**What:** Add `guest_exec`, `load_topology`, `json_output`, `exit_noop`,
`exit_error` as exported functions. Consolidate `load_auth` here.

**Why:** This is the library that Layer 2 tools import. Without these
functions, both `coolify_tool.py` and future application tools will
re-implement them.

### 2. `scripts/proxmox_tool.py`

**What:**
- Remove `command_coolify_db_exec`, `command_coolify_clear_cache`,
  `command_coolify_migrate_apps`, `command_coolify_install_deploy_key`.
- Remove the corresponding subparsers.
- Add deprecation warnings (stderr only) if these commands are invoked
  for one release cycle, redirecting to `coolify_tool.py`.
- Replace local `load_auth` with `controller_automation_toolkit.load_auth`.
- Expose `ProxmoxClient.guest_exec` through the toolkit (or keep in
  `proxmox_tool.py` and re-export from toolkit).

### 3. `scripts/coolify_tool.py`

**What:**
- Add `command_db_exec`, `command_clear_cache`, `command_migrate_apps`,
  `command_install_deploy_key` subcommands (migrated from `proxmox_tool.py`).
- Replace local `load_auth` with `controller_automation_toolkit.load_auth`.
- Import `controller_automation_toolkit.guest_exec` for operations that
  require guest-level execution.
- Add `--vmid` and `--env` flags where needed for guest-exec operations.

### 4. `playbooks/coolify.yml`

**What:** Update the two tasks added in ADR 0340 that call
`proxmox_tool.py coolify-install-deploy-key` and
`proxmox_tool.py coolify-migrate-apps` to call
`coolify_tool.py install-deploy-key` and `coolify_tool.py migrate-apps`
respectively.

### 5. `tests/test_proxmox_tool.py`

**What:** Remove tests for coolify-specific commands (they move to
`tests/test_coolify_tool.py`). Confirm remaining tests cover only
`guest-exec`, `docker-ps`, `install-key`.

### 6. `tests/test_coolify_tool.py`

**What:** Add tests for the migrated commands (`db-exec`, `clear-cache`,
`migrate-apps`, `install-deploy-key`) using the same `FakeGuestExec`
mock pattern established in `test_proxmox_tool.py`.

### 7. `docs/operator-tool-contract.md`

**What:** Document the three-layer architecture with a dependency diagram.
Include the list of which commands live in which tool.

## Consequences

### Positive

- `proxmox_tool.py` becomes a thin, stable CLI over the QAPI transport.
  It will rarely need changes as new services are added.
- `coolify_tool.py` becomes the single entry point for all Coolify
  operations, regardless of whether they go via REST API or guest exec.
  Operators and playbooks have one tool to reach for.
- The shared toolkit (`controller_automation_toolkit.py`) accumulates
  battle-tested primitives that future service tools inherit for free.
- Adding a new service tool (`vikunja_tool.py`, `woodpecker_tool.py`) is
  a Layer 2 addition that reuses Layer 1 primitives without touching
  `proxmox_tool.py`.

### Negative / Trade-offs

- The migration requires coordinated changes to `proxmox_tool.py`,
  `coolify_tool.py`, `controller_automation_toolkit.py`, two test files,
  and two playbook tasks — a non-trivial surface.
- The deprecation alias period means `proxmox_tool.py` temporarily
  contains dead code that could mislead future readers.
- Playbook tasks must be updated to use the new command names; any
  out-of-tree scripts that call `proxmox_tool.py coolify-*` will break
  after the deprecation period without warning.

## Implementation Order

1. Implement shared toolkit additions (`load_auth`, `guest_exec`, output helpers).
2. Migrate `coolify_tool.py` to use toolkit `load_auth` and add guest-exec-backed commands.
3. Update `playbooks/coolify.yml` to call the new `coolify_tool.py` commands.
4. Update tests.
5. Remove coolify commands from `proxmox_tool.py` (add deprecation aliases).
6. Remove `proxmox_tool.py` local `load_auth`.

## Related ADRs

- ADR 0039: Shared Controller Automation Toolkit
- ADR 0085: IaC Boundary
- ADR 0340: Dedicated Coolify Apps VM Separation
- ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI
- ADR 0343: Operator Tool Interface Contract
- ADR 0344: Single-Source Environment Topology
