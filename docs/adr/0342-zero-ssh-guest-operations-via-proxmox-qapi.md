# ADR 0342: Zero-SSH Guest Operations via Proxmox QAPI

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.4
- Implemented In Platform Version: 0.130.97
- Implemented On: 2026-04-04
- Date: 2026-04-04
- Tags: proxmox, automation, tooling, qapi, guest-exec, multi-environment, no-ssh

## Context

Controller-to-VM command execution has historically been performed via direct
SSH: the controller opens an SSH connection to a known IP, authenticates with
a private key stored in `.local/ssh/`, and runs commands. This approach has
four compounding problems at multi-environment scale:

1. **Key distribution.** Every new environment (staging, dev) requires its own
   SSH key pair, authorised on every target VM, stored on the controller, and
   rotated independently.

2. **Network reachability.** The controller must have TCP port 22 reachable to
   each VM's IP. On isolated Proxmox guest networks (e.g. `10.10.10.0/24`)
   this requires either an SSH jump host or a Tailscale route per VM.

3. **No idempotency guarantees.** Raw SSH commands have no structured return
   contract (no exit code mapping, no JSON output, no retry semantics). Each
   ad-hoc SSH invocation is hand-crafted and untested.

4. **Scaling to dev/staging/prod.** When prod, staging, and dev environments
   each contain 10–20 VMs, a matrix of SSH keys × VMs × environments becomes
   unmanageable without dedicated secrets infrastructure.

The Proxmox REST API exposes the QEMU Guest Agent (QGA) exec interface:
`POST /nodes/{node}/qemu/{vmid}/agent/exec` combined with polling
`GET /nodes/{node}/qemu/{vmid}/agent/exec-status?pid={pid}`. This provides
structured, authenticated, in-band command execution inside any VM that has
the QEMU guest agent installed—which all repo-managed VMs do via the
`linux_guest_runtime` role.

The Proxmox API is already authenticated via a PVE API token stored in
`.local/proxmox-api/<token>.json`. No additional secrets are required.
The same token grants access across all VMs on the node regardless of
the VM's internal network topology.

## Decision

All controller-initiated imperative operations targeting VM guests will use the
Proxmox QAPI guest-exec path (`ProxmoxClient.guest_exec`) rather than direct
SSH, unless SSH is the explicit subject of the operation (e.g. installing an
SSH key).

A new operator tool, `scripts/proxmox_tool.py`, provides the canonical
`ProxmoxClient` implementation and the `guest-exec` primitive. Shared
platform tools (`coolify_tool.py`, future service tools) access guest-exec
via primitives in `controller_automation_toolkit.py` — not by shelling out
to `proxmox_tool.py`.

### The `guest_exec` primitive contract

```python
def guest_exec(
    vmid: int,
    command: list[str],
    timeout: int = 60,
) -> tuple[int, str, str]:
    """
    Execute `command` inside VM `vmid` via the Proxmox QAPI exec interface.

    Returns (returncode, stdout, stderr).
    Raises RuntimeError on timeout or API error.
    Idempotent: repeated calls with the same command produce independent runs.
    """
```

The caller is responsible for idempotency of the wrapped command.
`guest_exec` itself makes no assumptions about the semantics of the command.

### Auth and topology resolution

The `ProxmoxClient` is constructed from a single JSON auth file:

```json
{
  "api_url": "https://<proxmox-host>:8006/api2/json",
  "authorization_header": "PVEAPIToken=<token_id>=<secret>"
}
```

This is the existing format used by `.local/proxmox-api/lv3-automation-primary.json`.
No new credential format is introduced.

Network reachability is handled by the `api_url` field in the per-environment
topology file (ADR 0344). For the Tailscale-accessible Proxmox node this is
`https://100.64.0.1:8006/api2/json`.

### Scope of zero-SSH migration

The following operation classes migrate to QAPI guest-exec immediately:

| Operation | Old method | New method |
|---|---|---|
| `docker ps` on a guest | `ssh root@<ip> docker ps` | `guest_exec(vmid, ["docker", "ps", ...])` |
| Install SSH public key into authorized_keys | `ssh` or cloud-init | `guest_exec(vmid, ["bash", "-c", "echo <key> >> /root/.ssh/authorized_keys"])` |
| Run `psql` query inside a container | `ssh root@<ip> docker exec <ct> psql ...` | `guest_exec(vmid, ["docker", "exec", ct, "psql", ...])` |
| Clear Coolify cache | `ssh root@<ip> docker exec coolify php artisan cache:clear` | `guest_exec(vmid, ["docker", "exec", "coolify", "php", "artisan", "cache:clear"])` |

Operations that inherently require SSH (configuring authorized_keys, testing
SSH connectivity to a newly registered Coolify server) are explicitly exempted.

### Error and timeout handling

- `guest_exec` polls `exec-status` with 1-second intervals.
- Timeout (default 60 s, configurable per call) raises `RuntimeError`.
- Non-zero exit codes from the guest command are returned as-is in `returncode`;
  the caller decides whether to raise or handle.
- API-level errors (HTTP 4xx/5xx, QGA not running) raise `RuntimeError` with
  the Proxmox error payload included.

### Multi-environment topology

The `ProxmoxClient` is instantiated per-environment from the topology file
(ADR 0344). Different environments map to different `api_url` values and
different VMIDs, but the same `guest_exec` interface. No code changes are
needed to support a new environment — only a new topology entry.

## Places That Need to Change

### 1. `scripts/proxmox_tool.py` — implemented

`ProxmoxClient` with `guest_exec` is implemented. Exposes CLI commands:
`guest-exec`, `docker-ps`, `install-key`.

### 2. `scripts/controller_automation_toolkit.py`

**What:** Expose `guest_exec` as a shared primitive. Tools that need to run
commands inside VMs import this function rather than constructing their own
`ProxmoxClient`.

```python
# controller_automation_toolkit.py
def guest_exec(
    auth: dict,
    node: str,
    vmid: int,
    command: list[str],
    timeout: int = 60,
) -> tuple[int, str, str]: ...
```

**Why:** Prevents each tool from duplicating the polling loop and error
handling. ADR 0039 mandates that shared primitives live in the toolkit.

### 3. `scripts/coolify_tool.py` — Coolify-specific guest operations

**What:** The `coolify-db-exec`, `coolify-clear-cache`, `coolify-migrate-apps`,
and `coolify-install-deploy-key` commands, currently in `proxmox_tool.py`,
belong in `coolify_tool.py`. They should call `controller_automation_toolkit.guest_exec`
rather than shelling out to `proxmox_tool.py`.

**Why:** See ADR 0345 (layered tool separation). Proxmox-layer tools should
not know about Coolify database schema or cache commands.

### 4. All repo runbooks

**What:** Any runbook step that says `ssh root@<ip> ...` for imperative VM
operations should be updated to show the equivalent `proxmox_tool.py guest-exec`
invocation or the Ansible task equivalent.

### 5. `tests/test_proxmox_tool.py` — implemented

26-test suite covering `guest_exec` polling, timeout, all CLI commands.
Coolify-specific commands should be moved to `tests/test_coolify_tool.py`
when those commands migrate (ADR 0345).

## Consequences

### Positive

- A single Proxmox API token grants zero-SSH access to all VMs in an
  environment. Adding a new environment means adding one topology entry,
  not distributing SSH keys.
- `guest_exec` returns structured `(rc, stdout, stderr)` — enabling proper
  error handling, retry logic, and test doubles.
- The controller never needs direct network paths to VM IPs (only to the
  Proxmox API endpoint, which is Tailscale-accessible).
- CI can mock `guest_exec` without network access; the existing 26-test suite
  demonstrates this pattern.

### Negative / Trade-offs

- Requires QEMU guest agent to be installed and running inside each VM
  (already guaranteed by `linux_guest_runtime` role).
- `guest_exec` output is buffered — very long-running commands should be
  split into smaller operations or use a timeout-aware loop.
- Proxmox QAPI exec does not support interactive TTY; commands must be
  non-interactive (pass `-y` flags, avoid pagers).

## Related ADRs

- ADR 0039: Shared Controller Automation Toolkit
- ADR 0085: IaC Boundary
- ADR 0183: Multi-Environment Inventory
- ADR 0214: HA Cells
- ADR 0340: Dedicated Coolify Apps VM Separation
- ADR 0343: Operator Tool Interface Contract
- ADR 0344: Single-Source Environment Topology
- ADR 0345: Layered Tool Separation
