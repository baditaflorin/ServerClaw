# Workstream ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy

- ADR: [ADR 0106](../adr/0106-ephemeral-environment-lifecycle-policy.md)
- Title: Govern the 910-979 ephemeral VM pool with expiry tags, capacity reservation, cluster-aware reaping, and operator-visible status
- Status: live_applied
- Implemented In Repo Version: 0.97.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Branch: `codex/ws-0106-live-apply`
- Worktree: `.worktrees/ws-0106-live-apply`
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

## Expected Repo Surfaces

- [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_ephemeral_vmid.py)
- [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py)
- [scripts/generate_ops_portal.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_ops_portal.py)
- [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json)
- [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/ephemeral-vm-reaper.py)
- [docs/runbooks/ephemeral-fixtures.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ephemeral-fixtures.md)
- [docs/runbooks/scaffold-new-service.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/scaffold-new-service.md)

## Expected Live Surfaces

- Windmill workspace `lv3` contains the script `f/lv3/ephemeral_vm_reaper`
- Windmill schedule `f/lv3/ephemeral_vm_reaper_every_30m` is present and enabled
- the mounted worker checkout carries `/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json`
- a manual `run_wait_result` execution writes a `receipts/fixtures/reaper-run-*.json` summary on `docker-runtime-lv3`

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_ephemeral_vm_reaper.py tests/test_fixture_expiry_reaper.py tests/test_ephemeral_lifecycle_repo_surfaces.py tests/test_deadlock_repo_surfaces.py -q`
- `make syntax-check-windmill`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --limit docker-runtime-lv3 --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fephemeral_vm_reaper`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'cat /srv/proxmox_florin_server/receipts/fixtures/reaper-run-20260326T143309Z.json'`

## Live Apply Result

- repo-side lifecycle enforcement is complete
- repo-side validation covers the governed ephemeral range and capacity seed
- static operator visibility for active repo-managed ephemeral VMs exists
- the live Windmill schedule is enabled and a clean manual sweep returned `{"expired_vmids":[],"retagged_vmids":[],"skipped_vmids":[],"warned_vmids":[]}`
- the live worker now resolves Proxmox credentials through the mirrored repo-local token payload when the sandboxed job environment does not inherit the runtime env contract

## Merge Notes

- Protected integration files remain deferred to merge-to-`main`: `README.md`, `VERSION`, release sections in `changelog.md`, and `versions/stack.yaml`
- The 2026-03-26 converge reached worker-checkout sync, runtime secret refresh, Windmill startup, script sync, and schedule reconciliation. A no-log Windmill task failed once in the final schedule/healthcheck tail, but the equivalent schedule update loop and the seeded `f/lv3/windmill_healthcheck` plus `f/lv3/ephemeral_vm_reaper` API runs were replayed successfully from the same branch state.
