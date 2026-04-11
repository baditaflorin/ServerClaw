# ADR 0343: Operator Tool Interface Contract

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.5
- Implemented On: 2026-04-04
- Date: 2026-04-04
- Tags: tooling, contracts, automation, dry, idempotency, operator-tools

## Context

The `scripts/` directory contains 255+ operator tools. As the platform grows
toward multi-environment operation (dev/staging/prod per ADR 0214) and more
agentic automation paths consume these tools directly, inconsistent tool
interfaces cause compounding problems:

1. **Ansible `changed_when` brittleness.** Playbook tasks that call operator
   scripts use `changed_when: "'\"status\": \"changed\"' in result.stdout"`.
   This only works if the tool actually emits that JSON structure. Tools that
   print free-form text, emit YAML, or use a different status key silently
   break idempotency tracking.

2. **Exit code fragmentation.** Some tools exit 0 always. Some exit 1 on
   "already done." Some print errors to stdout instead of stderr. Without a
   documented convention, every Ansible `failed_when` expression is a
   one-off guess.

3. **Auth flag inconsistency.** Some tools use `--auth-file`, others read
   from environment variables with different names, others hardcode paths.
   A new tool author has no specification to follow.

4. **`load_auth()` duplication.** `coolify_tool.py` (line 439),
   `proxmox_tool.py` (line 86), and future tools each implement their own
   auth-file loader despite `controller_automation_toolkit.py` (ADR 0039)
   existing as the shared home for this primitive.

5. **Agentic consumption.** Claude Code agents and CI scripts that invoke
   operator tools need a stable interface contract they can rely on across
   all tools without reading each tool's source to understand its output
   format.

Without a written contract, each new tool re-invents its CLI surface, and
each Ansible task that calls it contains bespoke parsing logic.

## Decision

All `scripts/` operator tools that perform imperative platform operations
must conform to the **Operator Tool Interface Contract** defined below.
This contract is enforced by `tests/test_operator_tool_contract.py` for all
tools listed in the contract registry.

### Contract specification

#### 1. Exit codes

| Code | Meaning |
|------|---------|
| `0` | Operation completed; state was changed |
| `1` | Error — operation failed; stderr contains the reason |
| `2` | No-op — operation was already in the desired state; nothing changed |

Exit code 2 enables Ansible's `failed_when: result.rc not in [0, 2]` and
`changed_when: result.rc == 0` patterns without string-matching stdout.

#### 2. Stdout format

Stdout must be a single JSON object on one or more lines (valid JSON when
fully buffered). The object must contain at least:

```json
{"status": "<verb>"}
```

Where `<verb>` is one of: `"changed"`, `"created"`, `"deleted"`, `"migrated"`,
`"installed"`, `"no_op"`, `"error"` (error only when exit code 1 is ambiguous
and the tool cannot avoid stdout output alongside the error).

Additional fields may be added freely. No field removal is allowed without a
major version bump to the tool.

```json
// Exit 0 examples
{"status": "installed", "key_fingerprint": "SHA256:abc123", "target_vmid": 171}
{"status": "migrated", "migrated_count": 3, "from_server": "coolify", "to_server": "coolify-apps"}

// Exit 2 example
{"status": "no_op", "reason": "already_installed"}

// Exit 1 example (stderr contains the human message; stdout is optional)
{"status": "error", "code": "auth_file_not_found"}
```

#### 3. Stderr

Stderr is for human-readable progress, debug output, and error explanations.
Ansible playbooks must not parse stderr. Tools may emit any text to stderr.

#### 4. Auth flags

Tools that require authentication must accept:

```
--auth-file <path>    Path to JSON auth file. Overrides CONTROLLER_AUTH_FILE env var.
```

The environment variable `CONTROLLER_AUTH_FILE` is read when `--auth-file`
is not provided. Auth loading is always delegated to
`controller_automation_toolkit.load_auth(path)`.

#### 5. Idempotency

Every tool must be safe to run multiple times against the same target. A
second run when the desired state already exists must exit 2 with
`{"status": "no_op"}`. It must never error on a repeated run unless the
environment has changed unexpectedly.

#### 6. `load_auth()` must not be re-implemented

No tool may define its own `load_auth` function. The canonical implementation
is `controller_automation_toolkit.load_auth(path: str | Path) -> dict`.
Tools that duplicate this function must be refactored to import it.

### Contract registry

The contract applies to the following tools (initial list; extended as new
tools are added):

- `scripts/coolify_tool.py`
- `scripts/proxmox_tool.py`
- `scripts/keycloak_tool.py`
- `scripts/windmill_tool.py`
- `scripts/vikunja_tool.py`
- `scripts/woodpecker_tool.py`

New tools added to `scripts/` that accept `--auth-file` or perform state
mutations must be added to the registry before merging.

### Ansible usage pattern

The standard playbook pattern for any contract-compliant tool call:

```yaml
- name: Install SSH deploy key on coolify-apps
  ansible.builtin.command: >
    python3 scripts/proxmox_tool.py
    --auth-file "{{ proxmox_api_token_local_file }}"
    install-key
    --vmid 171
    --pubkey "{{ coolify_deploy_ssh_pubkey }}"
  register: result
  changed_when: result.rc == 0
  failed_when: result.rc not in [0, 2]
```

No `stdout` string-matching is required when exit codes are used correctly.

## Places That Need to Change

### 1. `scripts/controller_automation_toolkit.py`

**What:** Add `load_auth(path) -> dict` as an exported function (move or
consolidate from wherever it currently lives in the toolkit). Confirm it
validates required keys and raises `SystemExit(1)` with a clear message on
missing file or missing keys.

**Why:** This is the single canonical implementation that all tools must use.

### 2. `scripts/coolify_tool.py`

**What:**
- Remove the local `load_auth()` definition (line 439).
- Import and call `controller_automation_toolkit.load_auth`.
- Audit exit codes: ensure all command functions exit 0/1/2 per contract.
- Audit stdout: ensure all JSON output has a `status` key.

### 3. `scripts/proxmox_tool.py`

**What:**
- Remove the local `load_auth()` definition (line 86).
- Import and call `controller_automation_toolkit.load_auth`.
- Verify all commands exit 0/1/2 per contract (already mostly compliant).

### 4. `tests/test_operator_tool_contract.py` — new file

**What:** A contract compliance test that imports each registered tool,
runs it with `--help` to confirm `--auth-file` is present, and asserts
that representative commands emit valid JSON and use correct exit codes
via mock.

### 5. `docs/operator-tool-contract.md` — new file

**What:** Human-readable companion to this ADR. Published in the docs
portal. Contains the contract table, examples, and the migration checklist
for making an existing tool compliant.

## Consequences

### Positive

- Every new Ansible task that calls an operator tool can use the same
  two-line `changed_when` / `failed_when` pattern without reading the tool.
- Agents and CI can reliably parse `result.stdout | from_json` for any
  contract-compliant tool.
- `load_auth` duplication is eliminated across all tools.
- The registry acts as a discoverable list of all operator tools for
  documentation generation (ADR 0327).

### Negative / Trade-offs

- Existing tools not yet compliant (exit code 0 for no-op, no JSON stdout)
  require refactoring before they can be added to the registry.
- The contract test suite must be maintained as new tools are added; skipping
  this is the most likely way the contract erodes.
- Tools that currently print rich human-readable output to stdout must be
  updated to emit JSON instead, and move human output to stderr — potentially
  a breaking change for operators who read stdout directly.

## Migration Checklist

For each tool being brought into compliance:

- [ ] Remove local `load_auth()` definition; import from `controller_automation_toolkit`
- [ ] Map all exit paths to exit code 0 / 1 / 2
- [ ] Ensure stdout is a single JSON object with a `status` key
- [ ] Move all human-readable output to stderr
- [ ] Add tool to contract registry in this ADR and in `tests/test_operator_tool_contract.py`
- [ ] Update any Ansible tasks calling the tool to use the `rc`-based pattern

## Related ADRs

- ADR 0039: Shared Controller Automation Toolkit
- ADR 0085: IaC Boundary
- ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI
- ADR 0344: Single-Source Environment Topology
- ADR 0345: Layered Tool Separation
