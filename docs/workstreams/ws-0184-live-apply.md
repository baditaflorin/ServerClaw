# Workstream WS-0184: Failure-Domain Labels And Anti-Affinity Policy Live Apply

- ADR: [ADR 0184](../adr/0184-failure-domain-labels-and-anti-affinity-policy.md)
- Title: Make failure-domain labels and anti-affinity policy enforced repo truth, then converge the live Proxmox labels from an isolated latest-main worktree
- Status: live_applied
- Implemented In Repo Version: 0.177.18
- Live Applied In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0184-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0184-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0180-standby-capacity`, `adr-0183-auxiliary-cloud-failure-domain`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox-host.yml`, `config/environment-topology.json`, `roles/proxmox_guests/`, `collections/ansible_collections/lv3/platform/roles/proxmox_guests/`, `scripts/failure_domain_policy.py`, `scripts/validate_repository_data_models.py`, `docs/runbooks/failure-domain-policy.md`, `receipts/live-applies/`

## Scope

- declare explicit failure-domain and anti-affinity metadata for the managed Proxmox guests and the active staging preview lane
- enforce the ADR 0184 policy in repository validation and expose a focused operator report for placement review
- converge the live Proxmox guest tags so the failure-domain labels are visible on the running platform
- capture verification evidence, live-apply receipts, and merge-safe handoff notes without touching protected integration files on this branch

## Non-Goals

- claiming cross-host redundancy before a second active failure domain exists
- implementing a full allocator or automatic workload scheduler
- updating protected main-only release files on this workstream branch

## Expected Repo Surfaces

- `inventory/host_vars/proxmox-host.yml`
- `config/environment-topology.json`
- `docs/schema/environment-topology.schema.json`
- `roles/proxmox_guests/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_guests/tasks/main.yml`
- `scripts/failure_domain_policy.py`
- `scripts/validate_repository_data_models.py`
- `tests/test_failure_domain_policy.py`
- `docs/runbooks/failure-domain-policy.md`
- `docs/adr/0184-failure-domain-labels-and-anti-affinity-policy.md`
- `receipts/live-applies/`

## Expected Live Surfaces

- each managed production guest advertises repo-derived Proxmox tags for failure domain, placement class, and anti-affinity group
- standby and recovery guests with temporary same-domain waivers expose that waiver visibly in their live labels
- the staging lane declares preview placement metadata that protects standby and recovery capacity in repo truth

## Verification

- `uv run --with pyyaml python scripts/failure_domain_policy.py --validate`
- `uv run --with pytest --with jsonschema --with pyyaml pytest -q tests/test_failure_domain_policy.py tests/test_validate_service_catalog.py tests/test_service_redundancy.py tests/test_standby_capacity.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/proxmox-install.yml --syntax-check --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
- `ANSIBLE_HOST_KEY_CHECKING=False make provision-guests`
  - expected to fail on the existing host drift because `postgres-replica` (`151`) is absent and template `9002` is unavailable
- `LV3_RUN_ID=ws0184labels ./scripts/run_with_namespace.sh ansible-playbook -i inventory/hosts.yml playbooks/site.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 --tags guests -e @.local/ws-0184-proxmox-guests-active.json`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from ansible-core ansible -i inventory/hosts.yml proxmox-host -b -m shell -a 'for vmid in 110 120 130 140 150 160; do printf "vmid=%s " "$vmid"; qm config "$vmid" | grep "^tags:"; done' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`

## Outcome

- the repo now enforces ADR 0184 through explicit guest and preview-lane placement metadata, a focused validation/report script, and generated platform vars
- live Proxmox labels are verified on the existing managed guests `110/120/130/140/150/160`
- the current host still lacks `postgres-replica` (`151`), so the standby-specific live label remains documented repo truth rather than a verified runtime object until that drift is repaired
- the workstream merged to `origin/main` on 2026-03-28 in repo version `0.177.18`

## Post-Merge Notes

- the `main` integration step advanced the repository release metadata to `0.177.18`
- `versions/stack.yaml` intentionally keeps platform version `0.130.31` because no fresh mainline live apply was required to preserve the already-verified branch-local platform state
- the stock `make provision-guests` replay still exposes pre-existing PostgreSQL standby drift on the host: `qm status 151` fails and template `9002` is absent
- a scoped replay against the guests that actually exist applied the ADR 0184 tags cleanly, and `backup` then required one explicit `qm set 160 --tags ...` follow-up so its recovery tags matched the repo policy
- the release-integrated branch-local receipt for this workstream remains `receipts/live-applies/2026-03-27-adr-0184-failure-domain-labels-live-apply.json`
