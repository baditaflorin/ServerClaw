# Workstream ADR 0183: Multi-Environment Live Lanes

- ADR: [ADR 0183](../adr/0183-multi-environment-live-lanes.md)
- Title: Make environment lanes catalog-driven, add a controlled staging activation path, and leave room for future development lanes without hardcoded rewrites
- Status: active
- Branch: `codex/adr-0183-multi-environment-lanes`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0183-multi-environment-lanes`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`, `adr-0073-promotion-pipeline`, `adr-0079-playbook-decomposition`, `adr-0182-live-apply-merge-train`
- Conflicts With: none
- Shared Surfaces: `config/environment-topology.json`, `inventory/host_vars/proxmox_florin.yml`, `roles/proxmox_network/`, `playbooks/proxmox-staging-bridge.yml`, `scripts/environment_*.py`, `scripts/lv3_cli.py`, `docs/runbooks/staging-environment.md`

## Scope

- add a dedicated ADR for environment-lane activation and extension
- make environment-aware tooling derive supported lanes from the environment topology catalog where safe
- add the missing Proxmox host bridge automation for the staging subnet
- document the operator path for bringing staging up from `main`

## Non-Goals

- claiming that staging is already live
- rolling out a dedicated long-lived development estate in the same turn
- replacing the explicit staging-to-production promotion semantics of ADR 0073

## Expected Repo Surfaces

- `docs/adr/0183-multi-environment-live-lanes.md`
- `docs/workstreams/adr-0183-multi-environment-live-lanes.md`
- `docs/runbooks/staging-environment.md`
- `config/environment-topology.json`
- `docs/schema/environment-topology.schema.json`
- `scripts/environment_catalog.py`
- `scripts/environment_topology.py`
- `inventory/host_vars/proxmox_florin.yml`
- `roles/proxmox_network/`
- `playbooks/proxmox-staging-bridge.yml`
- `Makefile`

## Expected Live Surfaces

- `vmbr20` can be applied intentionally from `main`
- the Proxmox host advertises the staging subnet after network convergence
- staging VM declarations can be reviewed and applied through the existing OpenTofu workflow

## Verification

- `python3 scripts/environment_topology.py --validate`
- `python3 scripts/live_apply_receipts.py list`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/services/grafana.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=staging -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- `python3 scripts/integration_suite.py --mode gate --environment staging`

## Notes For The Next Assistant

- do not mark the staging lane live until `vmbr20` exists on the Proxmox host and at least one staged VM is reachable
- keep promotion logic explicitly `staging -> production` even if general environment selection becomes catalog-driven elsewhere
- if a future `development` lane is added, prefer a narrow fixture-backed or controller-local model first instead of another long-lived VM fleet
