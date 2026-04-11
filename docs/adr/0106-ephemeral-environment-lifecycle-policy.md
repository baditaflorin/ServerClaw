# ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.97.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Date: 2026-03-23

## Context

ADR 0088 defines ephemeral infrastructure fixtures for testing and validation. It establishes how to provision an ephemeral VM on the staging network and run tests against it. What ADR 0088 does not define is the **lifecycle governance**:

- How long may an ephemeral VM exist before it must be torn down?
- Who is responsible for tearing it down if the workflow that created it fails midway?
- How are ephemeral VMs identified as ephemeral (vs. staging or production VMs)?
- What resources are reserved for ephemeral VMs and how does ephemeral capacity interact with the capacity model (ADR 0105)?
- What is the policy when an operator manually creates a VM in the Proxmox UI for temporary use?

Without these policies, ephemeral VMs accumulate. This is the "staging environment rot" problem: resources provisioned for temporary use become permanent because:
1. The cleanup step was never implemented
2. The workflow that created the VM failed before reaching the cleanup step
3. An operator manually created a VM and forgot about it
4. The VM was intentionally left running "just for a bit" and that bit became months

The platform already uses VMID range 900–909 for restore verification tests (ADR 0099). A broader ephemeral VM lifecycle policy is needed.

## Decision

We will establish a formal ephemeral environment lifecycle policy with a defined VMID range, a maximum lifetime enforced by an automated reaper, a mandatory ownership tag, and capacity accounting within the capacity model (ADR 0105).

### VMID allocation for ephemeral VMs

| VMID range | Purpose |
|---|---|
| 100–199 | Production VMs (managed by OpenTofu, ADR 0085) |
| 200–299 | Staging VMs (managed by OpenTofu) |
| 900–909 | Restore verification VMs (ADR 0099; always short-lived) |
| 910–979 | General ephemeral VMs (this ADR) |
| 980–999 | Reserved for future use |

Ephemeral VMs are always in VMID range 910–979. A VMID in this range is definitionally ephemeral; no other context is required to identify it.

### Mandatory ownership tag

Every ephemeral VM must be created with a Proxmox VM tag indicating its owner and purpose:

```
ephemeral-<owner>-<purpose>-<expires_epoch>
```

Example: `ephemeral-codex-adr0111-test-1743321600` (expires 2026-03-30 00:00 UTC).

The `lv3 fixture create` command (from ADR 0088) enforces this tagging:

```python
def create_ephemeral_vm(purpose: str, lifetime_hours: int = 4, owner: str = current_user()) -> EphemeralVm:
    if lifetime_hours > MAX_LIFETIME_HOURS:
        raise ValueError(f"Ephemeral VMs may not exceed {MAX_LIFETIME_HOURS} hours")
    expires = int((datetime.utcnow() + timedelta(hours=lifetime_hours)).timestamp())
    tag = f"ephemeral-{owner}-{purpose}-{expires}"
    vmid = allocate_ephemeral_vmid()
    create_vm(vmid=vmid, tags=[tag], network="vmbr20")
    record_in_audit_log("ephemeral_vm_created", vmid=vmid, purpose=purpose, expires=expires)
    return EphemeralVm(vmid=vmid, expires_at=expires)
```

### Maximum lifetimes

| Context | Maximum lifetime |
|---|---|
| Restore verification (ADR 0099) | 2 hours (hard) |
| Integration test fixture (ADR 0111) | 1 hour (hard) |
| ADR development and manual testing | 8 hours (soft — reaper warns at 6 h, destroys at 8 h) |
| Operator-declared extended fixture | 24 hours (requires explicit `--extend` flag and audit log entry) |

No ephemeral VM may live longer than 24 hours. If a test scenario requires a longer-lived environment, it is a staging VM (VMID 200–299), not an ephemeral fixture.

### Automated reaper

A Windmill workflow `ephemeral-vm-reaper` runs every 30 minutes:

```python
@windmill_flow(name="ephemeral-vm-reaper", schedule="*/30 * * * *")
def reaper():
    proxmox = ProxmoxAPI()
    now = int(datetime.utcnow().timestamp())

    for vm in proxmox.list_vms():
        if vm.vmid not in EPHEMERAL_VMID_RANGE:
            continue

        expires = parse_expiry_from_tags(vm.tags)
        if expires is None:
            # Untagged ephemeral VM — warn and schedule for destruction in 1 hour
            emit_warning(f"Ephemeral VM {vm.vmid} has no expiry tag; will be destroyed in 1 hour")
            tag_with_expiry(vm.vmid, now + 3600)
            continue

        if now > expires:
            proxmox.stop_vm(vm.vmid)
            proxmox.destroy_vm(vm.vmid)
            record_in_audit_log("ephemeral_vm_reaped", vmid=vm.vmid)
            notify_mattermost(f"♻️ Reaped expired ephemeral VM {vm.vmid} ({vm.name})")
```

The reaper also handles VMs in the ephemeral range that have no expiry tag — these are manually created VMs that bypassed the tagging requirement. They are given a 1-hour grace period and then destroyed.

### Capacity accounting

The capacity model (ADR 0105) reserves a fixed allocation for the ephemeral VM pool:

```json
{
  "ephemeral_pool": {
    "vmid_range": [910, 979],
    "max_concurrent_vms": 5,
    "reserved_ram_gb": 20,
    "reserved_vcpu": 8,
    "reserved_disk_gb": 100,
    "notes": "Resource budget for all ephemeral fixtures; shared across restore tests, integration tests, and ADR development"
  }
}
```

If creating an ephemeral VM would exceed the pool's resource budget, `lv3 fixture create` fails with a clear error. The operator must either wait for existing ephemeral VMs to be reaped or explicitly extend an existing fixture.

### Staging VM governance

Staging VMs (VMID 200–299) are not ephemeral — they are managed by OpenTofu (ADR 0085) and have the same lifecycle as production VMs. They may only be created by an ADR workstream that explicitly provisions them. The staging environment (ADR 0072) defines which staging VMs exist permanently; no operator may add a staging VM outside of this process.

### Ops portal integration

The ops portal (ADR 0093) includes an **Ephemeral VMs** panel showing:
- All currently running ephemeral VMs with VMID, purpose, owner, and time-to-expiry
- A "Extend" button (adds 2 hours, requires confirmation)
- A "Destroy now" button (immediate destruction with audit log entry)

## Consequences

**Positive**
- Ephemeral VM accumulation is impossible; the reaper ensures cleanup even when workflows fail midway
- Resource reservation in the capacity model means ephemeral test activity cannot starve production workloads
- The VMID range convention makes ephemeral VMs immediately identifiable in the Proxmox UI without any additional lookup
- The audit log records every creation and destruction; there is a complete history of ephemeral VM usage

**Negative / Trade-offs**
- The reaper runs every 30 minutes; an expired VM may continue to run for up to 30 minutes past its expiry — this is acceptable; if an exact expiry is required, the workflow should destroy the VM explicitly
- The 24-hour maximum lifetime is a hard policy; legitimate use cases that need longer environments must use staging VMs, which have a higher change management overhead; this is intentional

## Alternatives Considered

- **Manual cleanup discipline**: rely on operators to clean up their own ephemeral VMs; provably insufficient; this is exactly the failure mode that led to staging environment rot
- **Kubernetes ephemeral environments (Namespace per PR)**: appropriate for containerised platforms; does not apply to VM-based workloads
- **No maximum lifetime; just tag with owner**: without enforcement, tags are informational only; the reaper is what transforms the tag from advice into policy

## Implementation Notes

- Repository implementation landed in `0.97.0` with the governed pool seed at [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/capacity-model.json), the lifecycle enforcement and cluster-aware reaper logic in [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/fixture_manager.py), the Windmill entrypoint [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/ephemeral-vm-reaper.py), and the range guard [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_ephemeral_vmid.py).
- The repo-managed `lv3 fixture create|destroy|list` route now exposes owner, purpose, lifetime, and VMID-aware teardown through [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/lv3_cli.py) and [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/Makefile).
- Operator visibility is currently delivered through the static ops-portal panel rendered by [scripts/generate_ops_portal.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/generate_ops_portal.py). This is an inference from the current repo state because ADR 0093's interactive portal is not implemented yet.
- The first verified live apply completed on `2026-03-26` from the isolated branch `codex/ws-0106-live-apply`. That rollout enabled and verified the Windmill schedule `f/lv3/ephemeral_vm_reaper_every_30m` and mirrored the Proxmox API token payload into the mounted worker checkout at `/srv/proxmox-host_server/.local/proxmox-api/lv3-automation-primary.json`.
- The rebased `main` release `0.175.1` advanced the live platform version to `0.130.22` on `2026-03-26`. The follow-up verification from the merged mainline state also fixed the Windmill sandbox write path by moving durable reaper-run summaries under `/srv/proxmox-host_server/.local/fixtures/reaper-runs/`, confirmed `f/lv3/ephemeral_vm_reaper` at hash `a2eed27d62fa68fc`, and recorded the clean manual sweep receipt `.local/fixtures/reaper-runs/reaper-run-20260326T170554Z.json`.
- The broader `playbooks/windmill.yml` replay from the integrated mainline state still failed later in unrelated raw-app sync for `f/lv3/operator_access_admin` with Docker reporting `unexpected EOF`, so the final ADR 0106 verification used a targeted worker-checkout refresh plus a targeted sync of `f/lv3/ephemeral_vm_reaper`. The ADR 0106 script, schedule, healthcheck, mirrored worker credential payload, and manual reaper path all verified successfully from the same integrated branch state.

## Related ADRs

- ADR 0072: Staging and production environment topology (staging VMs are governed separately)
- ADR 0085: OpenTofu VM lifecycle (production and staging VMs go through OpenTofu)
- ADR 0088: Ephemeral infrastructure fixtures (this ADR extends its lifecycle model)
- ADR 0093: Interactive ops portal (ephemeral VM panel)
- ADR 0099: Backup restore verification (restore VMs use the ephemeral pool)
- ADR 0105: Platform capacity model (ephemeral pool reserved in capacity model)
- ADR 0111: End-to-end integration test suite (integration test VMs use the ephemeral pool)
