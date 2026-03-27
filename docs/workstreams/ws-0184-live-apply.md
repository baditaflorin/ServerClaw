# Workstream WS-0184: Failure-Domain Labels And Anti-Affinity Policy Live Apply

- ADR: [ADR 0184](../adr/0184-failure-domain-labels-and-anti-affinity-policy.md)
- Title: Make failure-domain labels and anti-affinity policy enforced repo truth, then converge the live Proxmox labels from an isolated latest-main worktree
- Status: implemented
- Branch: `codex/ws-0184-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0184-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0180-standby-capacity`, `adr-0183-auxiliary-cloud-failure-domain`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `config/environment-topology.json`, `roles/proxmox_guests/`, `collections/ansible_collections/lv3/platform/roles/proxmox_guests/`, `scripts/failure_domain_policy.py`, `scripts/validate_repository_data_models.py`, `docs/runbooks/failure-domain-policy.md`, `receipts/live-applies/`

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

- `inventory/host_vars/proxmox_florin.yml`
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

- `python3 scripts/failure_domain_policy.py --validate`
- `uv run --with pytest pytest -q tests/test_failure_domain_policy.py tests/test_validate_service_catalog.py tests/test_service_redundancy.py tests/test_standby_capacity.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `ANSIBLE_HOST_KEY_CHECKING=False make provision-guests`
- `ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@65.108.75.123 sudo qm config 151`

## Notes For The Next Assistant

- Protected integration files still stay untouched here even if the live apply succeeds; merge-to-main must decide any `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` updates.
