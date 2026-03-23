# Workstream ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy

- ADR: [ADR 0106](../adr/0106-ephemeral-environment-lifecycle-policy.md)
- Title: VMID range 910–979 governance with mandatory expiry tags, automated reaper Windmill workflow, and ephemeral pool capacity reservation
- Status: ready
- Branch: `codex/adr-0106-ephemeral-lifecycle`
- Worktree: `../proxmox_florin_server-ephemeral-lifecycle`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`, `adr-0085-opentofu-vm-lifecycle`, `adr-0088-ephemeral-fixtures`, `adr-0093-interactive-ops-portal`, `adr-0105-capacity-model`
- Conflicts With: none
- Shared Surfaces: `scripts/fixture_manager.py` (if it exists from ADR 0088), Windmill workflows, `config/capacity-model.json`

## Scope

- update `scripts/fixture_manager.py` (from ADR 0088) or write `scripts/ephemeral_vm_manager.py` — adds `create_ephemeral_vm()` with mandatory tagging, `destroy_ephemeral_vm()`, and `allocate_ephemeral_vmid()` (scans VMID range 910–979 for free slot)
- write Windmill workflow `ephemeral-vm-reaper` — scheduled every 30 minutes; queries Proxmox for VMs in the ephemeral range, destroys expired ones, warns on untagged ones
- update `config/capacity-model.json` — add `ephemeral_pool` section with resource reservation
- add Grafana panel `Ephemeral VMs` to the ops portal integration or platform overview dashboard — shows current running ephemeral VMs with expiry times
- write `scripts/validate_ephemeral_vmid.py` — validates that no VMID in the ephemeral range appears in OpenTofu state (would indicate a staging VM accidentally placed in the wrong range)
- update `docs/runbooks/add-a-new-service.md` — add note about using ephemeral VMs for service testing during development
- add `lv3 fixture list` and `lv3 fixture destroy <vmid>` commands to platform CLI

## Non-Goals

- Ephemeral LXC containers (VMs only in this iteration)
- Per-operator ephemeral quotas (shared pool only)
- Automatic re-provisioning of expired fixtures

## Expected Repo Surfaces

- `scripts/ephemeral_vm_manager.py` (new or updated from ADR 0088)
- `config/capacity-model.json` (patched: `ephemeral_pool` section)
- Makefile (patched: `lv3 fixture list`, `lv3 fixture destroy`)
- `docs/adr/0106-ephemeral-environment-lifecycle-policy.md`
- `docs/workstreams/adr-0106-ephemeral-lifecycle.md`

## Expected Live Surfaces

- Windmill `ephemeral-vm-reaper` workflow is scheduled every 30 minutes and has at least one successful run
- `lv3 fixture create --purpose test --lifetime-hours 1` creates a VM in VMID range 910–979 with correct tags
- The VM is automatically destroyed within 30 minutes of its expiry time
- `lv3 fixture list` shows currently running ephemeral VMs

## Verification

- `lv3 fixture create --purpose adr-0106-test --lifetime-hours 1` → creates a VM; `qm list` shows it in VMID range 910–979
- Wait 60+ minutes (or manually trigger the reaper workflow); verify the VM is destroyed
- Create a VM without the expiry tag manually in the Proxmox UI in VMID range 910–979; trigger the reaper; verify Mattermost receives a warning and the VM gets a 1-hour grace tag
- `lv3 fixture list` shows the VM correctly

## Merge Criteria

- Reaper workflow deployed and scheduled in Windmill
- `lv3 fixture create` and `lv3 fixture destroy` commands work
- Reaper successfully destroys an expired test VM (end-to-end test)
- Capacity model updated with ephemeral pool reservation

## Notes For The Next Assistant

- Proxmox VM tags are set via `qm set <vmid> --tags <tag-list>` (comma-separated); the Proxmox API uses `proxmoxer` in Python: `proxmox.nodes('florin').qemu(vmid).config.put(tags='ephemeral-codex-test-1234567890')`
- The reaper must not destroy VMs that are currently being used by an active Windmill workflow; check if a Windmill job referencing the VMID is currently running before destroying it (via Windmill jobs API)
- VMID allocation: scan from 910 to 979 and return the first VMID not in `qm list` output; add a small lock file or atomic check to prevent race conditions if two workflows try to allocate simultaneously
- Warn in the reaper workflow if more than 3 untagged VMs are found in the ephemeral range simultaneously — this indicates the tagging policy is being bypassed and needs investigation
