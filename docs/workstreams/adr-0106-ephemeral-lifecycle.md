# Workstream ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy

- ADR: [ADR 0106](../adr/0106-ephemeral-environment-lifecycle-policy.md)
- Title: Govern the 910-979 ephemeral VM pool with expiry tags, capacity reservation, cluster-aware reaping, and operator-visible status
- Status: merged
- Branch: `codex/adr-0106-ephemeral-lifecycle`
- Worktree: `../proxmox_florin_server-ephemeral-lifecycle`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`, `adr-0085-opentofu-vm-lifecycle`, `adr-0088-ephemeral-fixtures`, `adr-0093-interactive-ops-portal`, `adr-0105-capacity-model`
- Conflicts With: none
- Shared Surfaces: `scripts/fixture_manager.py`, `scripts/lv3_cli.py`, `scripts/generate_ops_portal.py`, `config/capacity-model.json`, `config/{command,workflow}-catalog.json`, `tests/fixtures/`

## Scope Delivered

- moved the governed ephemeral VM pool from the older fixture-local 9100-9199 range to `910-979`
- extended [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py) so `create/up` stamps owner, purpose, policy, and expiry tags onto every repo-managed ephemeral VM
- added capacity enforcement against [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json) before a new ephemeral VM is allocated
- made `fixture list` cluster-aware so it shows current ephemeral VMs by VMID, owner, purpose, remaining lifetime, and health
- added direct destroy support by VMID for ephemeral VMs that exist in the governed range even when no active receipt remains
- upgraded the reaper path to a cluster-aware sweep that retags unowned VMs in the ephemeral range with a one-hour grace period and destroys expired VMs
- added the repo guard [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_ephemeral_vmid.py) and wired the capacity-model check into [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py)
- exposed the new lifecycle surface through `lv3 fixture create|destroy|list` and added a static ops-portal panel for active repo-managed ephemeral VMs

## Non-Goals Still Out Of Scope

- Windmill job-awareness before reaping a currently-used VM
- per-operator quotas inside the shared pool
- a live platform claim that the reaper schedule is already enabled from `main`

## Expected Repo Surfaces

- [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_ephemeral_vmid.py)
- [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py)
- [scripts/generate_ops_portal.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_ops_portal.py)
- [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json)
- [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/ephemeral-vm-reaper.py)
- [docs/runbooks/ephemeral-fixtures.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ephemeral-fixtures.md)
- [docs/runbooks/scaffold-new-service.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/scaffold-new-service.md)

## Live Surfaces Still Pending

- the Windmill schedule for `ephemeral-vm-reaper` is not claimed as live from this repo-only merge
- no platform version bump is claimed because the host-side schedule and end-to-end live sweep were not applied from `main` in this workstream

## Verification Run

- `uvx --with pytest --with pyyaml --with jsonschema pytest tests/test_vmid_allocator.py tests/test_fixture_manager.py tests/test_fixture_expiry_reaper.py tests/test_ephemeral_vm_reaper.py tests/test_lv3_cli.py tests/test_ops_portal.py tests/test_validate_ephemeral_vmid.py`
- `uvx --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uvx --with pyyaml python scripts/validate_ephemeral_vmid.py --validate`
- `uvx --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --output-dir /tmp/ops-portal-0106 --health-snapshot tests/fixtures/ops_portal_health.json --probe-timeout 0 --write`

## Merge Criteria Result

- repo-side lifecycle enforcement is complete
- repo-side validation covers the governed ephemeral range and capacity seed
- static operator visibility for active repo-managed ephemeral VMs exists
- live enablement remains a follow-up from `main`
