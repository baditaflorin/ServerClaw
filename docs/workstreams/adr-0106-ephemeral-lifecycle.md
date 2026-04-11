# Workstream ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy

- ADR: [ADR 0106](../adr/0106-ephemeral-environment-lifecycle-policy.md)
- Title: Govern the 910-979 ephemeral VM pool with expiry tags, capacity reservation, cluster-aware reaping, and operator-visible status
- Status: merged
- Implemented In Repo Version: 0.97.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Branch: `codex/ws-0106-main-merge`
- Worktree: `.worktrees/ws-0106-main-merge`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`, `adr-0085-opentofu-vm-lifecycle`, `adr-0088-ephemeral-fixtures`, `adr-0093-interactive-ops-portal`, `adr-0105-capacity-model`
- Conflicts With: none
- Shared Surfaces: `scripts/fixture_manager.py`, `scripts/lv3_cli.py`, `scripts/generate_ops_portal.py`, `config/capacity-model.json`, `config/{command,workflow}-catalog.json`, `tests/fixtures/`

## Scope Delivered

- moved the governed ephemeral VM pool from the older fixture-local 9100-9199 range to `910-979`
- extended [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/fixture_manager.py) so `create/up` stamps owner, purpose, policy, and expiry tags onto every repo-managed ephemeral VM
- added capacity enforcement against [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/capacity-model.json) before a new ephemeral VM is allocated
- made `fixture list` cluster-aware so it shows current ephemeral VMs by VMID, owner, purpose, remaining lifetime, and health
- added direct destroy support by VMID for ephemeral VMs that exist in the governed range even when no active receipt remains
- upgraded the reaper path to a cluster-aware sweep that retags unowned VMs in the ephemeral range with a one-hour grace period and destroys expired VMs
- added the repo guard [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_ephemeral_vmid.py) and wired the capacity-model check into [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repository_data_models.py)
- exposed the new lifecycle surface through `lv3 fixture create|destroy|list` and added a static ops-portal panel for active repo-managed ephemeral VMs

## Non-Goals Still Out Of Scope

- Windmill job-awareness before reaping a currently-used VM
- per-operator quotas inside the shared pool

## Expected Repo Surfaces

- [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/fixture_manager.py)
- [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_ephemeral_vmid.py)
- [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/lv3_cli.py)
- [scripts/generate_ops_portal.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/generate_ops_portal.py)
- [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/capacity-model.json)
- [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/ephemeral-vm-reaper.py)
- [docs/runbooks/ephemeral-fixtures.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/ephemeral-fixtures.md)
- [docs/runbooks/scaffold-new-service.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/scaffold-new-service.md)

## Expected Live Surfaces

- Windmill workspace `lv3` contains the script `f/lv3/ephemeral_vm_reaper`
- Windmill schedule `f/lv3/ephemeral_vm_reaper_every_30m` is present and enabled
- the mounted worker checkout carries `/srv/proxmox-host_server/.local/proxmox-api/lv3-automation-primary.json`
- a manual `run_wait_result` execution writes a `.local/fixtures/reaper-runs/reaper-run-*.json` summary on `docker-runtime`

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_fixture_manager.py tests/test_ephemeral_vm_reaper.py tests/test_fixture_expiry_reaper.py tests/test_ephemeral_lifecycle_repo_surfaces.py tests/test_deadlock_repo_surfaces.py -q`
- `make syntax-check-windmill`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --limit docker-runtime --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fephemeral_vm_reaper`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime -m shell -a 'python3 - <<\"PY\"\nfrom pathlib import Path\nimport json\npayload = Path(\"/srv/proxmox-host_server/.local/proxmox-api/lv3-automation-primary.json\")\nlatest = sorted(Path(\"/srv/proxmox-host_server/.local/fixtures/reaper-runs\").glob(\"reaper-run-*.json\"))[-1]\nprint(json.dumps({\"payload_exists\": payload.exists(), \"latest_receipt\": latest.name, \"latest_receipt_body\": json.loads(latest.read_text())}, indent=2, sort_keys=True))\nPY' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`

## Live Apply Result

- repo-side lifecycle enforcement is complete
- repo-side validation covers the governed ephemeral range and capacity seed
- static operator visibility for active repo-managed ephemeral VMs exists
- the live Windmill schedule is enabled and a clean manual sweep returned `{"expired_vmids":[],"retagged_vmids":[],"skipped_vmids":[],"warned_vmids":[]}` while writing `.local/fixtures/reaper-runs/reaper-run-20260326T170554Z.json`
- the live worker now resolves Proxmox credentials through the mirrored repo-local token payload when the sandboxed job environment does not inherit the runtime env contract

## Merge Notes

- The mainline integration is complete in repository release `0.175.1`, and the integrated live verification advanced the platform version to `0.130.22` on `2026-03-26`.
- The integrated `playbooks/windmill.yml` replay reached worker-checkout sync, mirrored credential payload creation, Windmill startup, and script sync, but later failed in unrelated raw-app sync for `f/lv3/operator_access_admin` with Docker reporting `unexpected EOF`.
- The final ADR 0106 reapply therefore used a targeted worker-checkout refresh plus a targeted `f/lv3/ephemeral_vm_reaper` sync, after which direct `f/lv3/windmill_healthcheck` plus `f/lv3/ephemeral_vm_reaper` API runs both succeeded from the same integrated branch state.
