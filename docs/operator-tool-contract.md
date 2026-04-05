# Operator Tool Interface Contract

**Specification version:** 1.0
**ADR:** [0343](adr/0343-operator-tool-interface-contract.md)
**Last updated:** 2026-04-04

This document is the human-readable companion to ADR 0343. It defines the
interface that every imperative operator tool in `scripts/` must follow so
that Ansible playbooks, CI pipelines, and Claude Code agents can consume all
tools uniformly without reading each tool's source.

---

## 1. Exit Codes

| Code | Meaning |
|------|---------|
| `0` | **Changed** — the operation completed and state was modified |
| `1` | **Error** — the operation failed; stderr contains the reason |
| `2` | **No-op** — the desired state already existed; nothing was changed |

Exit code 2 is the key enabler for Ansible idempotency tracking. When a tool
exits 2 it means "I checked, everything is already correct, I did nothing."

### Why three codes?

Without exit code 2, Ansible must parse stdout to distinguish "I ran but did
nothing" from "I ran and made a change." String-matching stdout is fragile and
breaks silently when a tool's output wording changes. Exit codes are stable
primitives.

---

## 2. Stdout Format

All stdout from a contract-compliant tool is a single JSON object. The object
must contain at minimum a `"status"` key:

```json
{"status": "<verb>"}
```

Permitted verbs:

| Verb | Exit code | Meaning |
|------|-----------|---------|
| `"changed"` | 0 | Generic state mutation |
| `"created"` | 0 | New resource was created |
| `"deleted"` | 0 | Resource was removed |
| `"migrated"` | 0 | Resource was moved between hosts/services |
| `"installed"` | 0 | Software or configuration was installed |
| `"no_op"` | 2 | Already in desired state |
| `"error"` | 1 | Failed — used only when stdout output alongside the error is unavoidable |

Additional fields may be added freely. Existing fields must not be removed or
renamed without a major version bump to the tool.

### Examples

```json
// Exit 0 — key was installed
{
  "status": "installed",
  "key_fingerprint": "SHA256:abc123",
  "target_vmid": 171
}

// Exit 0 — VMs were migrated
{
  "status": "migrated",
  "migrated_count": 3,
  "from_server": "coolify-lv3",
  "to_server": "coolify-apps-lv3"
}

// Exit 2 — nothing to do
{
  "status": "no_op",
  "reason": "already_installed"
}

// Exit 1 — stderr has the human message; stdout JSON is optional
{
  "status": "error",
  "code": "auth_file_not_found"
}
```

### Parsing in Ansible

```yaml
- name: Read tool output
  ansible.builtin.set_fact:
    tool_result: "{{ result.stdout | from_json }}"
```

This works for any contract-compliant tool without bespoke parsing logic.

---

## 3. Stderr

Stderr is exclusively for human-readable output: progress messages, debug
information, and error explanations. Ansible playbooks **must not parse
stderr**. Tools may emit any text to stderr freely without breaking automation.

---

## 4. The `--auth-file` Flag and `CONTROLLER_AUTH_FILE`

Any tool that requires authentication must accept:

```
--auth-file <path>
```

When `--auth-file` is not provided, the tool reads the path from the
environment variable `CONTROLLER_AUTH_FILE`.

### Precedence

1. `--auth-file` CLI flag (highest priority)
2. `CONTROLLER_AUTH_FILE` environment variable
3. Tool-specific default (lowest priority, document explicitly if used)

### Auth loading

All auth loading must be delegated to the shared helpers in
`controller_automation_toolkit`:

```python
from controller_automation_toolkit import load_proxmox_auth, load_operator_auth

# For Proxmox tools (validates api_url + authorization_header keys):
auth = load_proxmox_auth(args.auth_file)

# For generic/multi-schema tools:
auth = load_operator_auth(args.auth_file)
```

No tool may define its own `load_auth` function. The canonical implementations
validate required keys and exit 1 with a clear error message if the file is
missing or malformed.

---

## 5. Idempotency Requirement

Every contract-compliant tool must be safe to run multiple times against the
same target.

- A **first run** when the desired state does not yet exist: exits 0.
- A **subsequent run** when the desired state already exists: exits 2 with
  `{"status": "no_op"}`.
- A tool must never return exit code 1 on a repeated run unless the
  environment itself has changed in an unexpected or error-producing way.

This requirement is what makes `changed_when: result.rc == 0` reliable.

---

## 6. Using the Toolkit Helpers

`controller_automation_toolkit` provides three output helpers that implement
the contract automatically.

### `tool_output(status, **fields)`

Writes a JSON object to stdout with the given status and any additional fields.
Does not exit.

```python
from controller_automation_toolkit import tool_output

tool_output("created", resource="vm-171", vmid=171)
# stdout: {"status": "created", "resource": "vm-171", "vmid": 171}
# Exit code: caller's responsibility
```

### `tool_exit_noop(**fields)`

Writes `{"status": "no_op", ...}` to stdout and calls `sys.exit(2)`.

```python
from controller_automation_toolkit import tool_exit_noop

if resource_already_exists:
    tool_exit_noop(reason="vm_already_present", vmid=171)
    # Never reaches here; exits 2
```

### `tool_exit_error(message, **fields)`

Writes `ERROR: <message>` to stderr and calls `sys.exit(1)`. If keyword
arguments are provided, also writes a JSON object with `"status": "error"` to
stdout.

```python
from controller_automation_toolkit import tool_exit_error

if not auth_file.exists():
    tool_exit_error("auth file not found", code="auth_file_not_found")
    # Never reaches here; exits 1
```

---

## 7. Migration Checklist

Use this checklist when bringing an existing tool into compliance with ADR 0343.

- [ ] **Remove local `load_auth()`** — delete the local definition and import
  `load_proxmox_auth` or `load_operator_auth` from
  `controller_automation_toolkit`.
- [ ] **Map exit paths to 0/1/2** — audit every `sys.exit()` call and every
  return path; ensure no-op paths exit 2, error paths exit 1, and change paths
  exit 0.
- [ ] **Ensure stdout is JSON with a `status` key** — replace any free-form
  print statements with `tool_output(...)` calls or equivalent `json.dumps`.
- [ ] **Move human output to stderr** — progress messages, verbose output, and
  confirmation text belong on stderr, not stdout.
- [ ] **Add `--auth-file` flag** — if the tool authenticates with any service,
  add the flag and wire it to `CONTROLLER_AUTH_FILE` as fallback.
- [ ] **Register the tool** — add the tool to the contract registry in ADR 0343
  and to `tests/test_operator_tool_contract.py`.
- [ ] **Update Ansible tasks** — change any playbook tasks that call the tool to
  use the `rc`-based pattern (see Section 8 below).
- [ ] **Run the contract tests** — `python3 -m pytest tests/test_operator_tool_contract.py -v`

---

## 8. Ansible Task Pattern

The standard playbook pattern for any contract-compliant tool:

```yaml
- name: Install SSH deploy key on coolify-apps-lv3
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

Key points:

- `changed_when: result.rc == 0` — Ansible marks the task as "changed" only
  when state was mutated; a no-op (exit 2) is correctly marked "ok".
- `failed_when: result.rc not in [0, 2]` — any exit code outside 0 or 2
  is a failure. Exit 1 from the tool becomes a playbook failure automatically.
- No stdout string-matching is required.

### Capturing tool output as a fact

```yaml
- name: Capture tool output
  ansible.builtin.set_fact:
    deploy_key_result: "{{ result.stdout | from_json }}"

- name: Show installed key fingerprint
  ansible.builtin.debug:
    msg: "Key fingerprint: {{ deploy_key_result.key_fingerprint }}"
  when: result.rc == 0
```

---

## 9. Contract Registry

The following tools are currently registered and must remain compliant:

| Tool | Location | Notes |
|------|----------|-------|
| Proxmox tool | `scripts/proxmox_tool.py` | |
| Coolify tool | `scripts/coolify_tool.py` | |
| Keycloak tool | `scripts/keycloak_tool.py` | |
| Windmill tool | `scripts/windmill_tool.py` | |
| Vikunja tool | `scripts/vikunja_tool.py` | |
| Woodpecker tool | `scripts/woodpecker_tool.py` | |
| Portainer tool | `scripts/portainer_tool.py` | |
| Plane tool | `scripts/plane_tool.py` | |
| Semaphore tool | `scripts/semaphore_tool.py` | |
| Uptime Kuma tool | `scripts/uptime_kuma_tool.py` | Previously used non-standard `load_auth_json`; now delegates to `load_operator_auth` from toolkit |

New tools added to `scripts/` that accept `--auth-file` or perform state
mutations must be added to this registry before merging.

---

## Related Documents

- [ADR 0343: Operator Tool Interface Contract](adr/0343-operator-tool-interface-contract.md)
- [ADR 0039: Shared Controller Automation Toolkit](adr/0039-shared-controller-automation-toolkit.md)
- [ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI](adr/0342-zero-ssh-guest-operations-via-proxmox-qapi.md)
- [ADR 0344: Single-Source Environment Topology](adr/0344-single-source-environment-topology.md)
- [ADR 0345: Layered Operator Tool Separation](adr/0345-layered-operator-tool-separation.md)
