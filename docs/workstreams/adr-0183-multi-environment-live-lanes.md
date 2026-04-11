# Workstream ADR 0183: Multi-Environment Live Lanes

- ADR: [ADR 0183](../adr/0183-multi-environment-live-lanes.md)
- Title: Make environment lanes catalog-driven, add a controlled staging activation path, and leave room for future development lanes without hardcoded rewrites
- Status: live_applied
- Implemented In Repo Version: 0.177.9
- Live Applied In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/adr-0183-main-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0183-main-live-apply`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`, `adr-0073-promotion-pipeline`, `adr-0079-playbook-decomposition`, `adr-0182-live-apply-merge-train`
- Conflicts With: none
- Shared Surfaces: `config/environment-topology.json`, `inventory/host_vars/proxmox-host.yml`, `roles/proxmox_network/`, `playbooks/proxmox-staging-bridge.yml`, `scripts/environment_*.py`, `scripts/lv3_cli.py`, `docs/runbooks/staging-environment.md`

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
- `inventory/host_vars/proxmox-host.yml`
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
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/services/grafana.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=staging -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- `python3 scripts/integration_suite.py --mode gate --environment staging`

## Notes For The Next Assistant

- the staging lane is now live on `vmbr20` with VMIDs `220` and `240`, and both staged guests are reachable over SSH through the Proxmox jump
- keep promotion logic explicitly `staging -> production` even if general environment selection becomes catalog-driven elsewhere
- if a future `development` lane is added, prefer a narrow fixture-backed or controller-local model first instead of another long-lived VM fleet
- `make remote-tofu-apply ENV=staging` still hit the build-server session-runtime ownership bug during the first live activation; the successful replay repaired ownership on the session-scoped plan directory and executed `scripts/tofu_exec.sh apply staging` directly on `docker-build`
- repository version `0.177.12` codifies `network_firewall = false` for the staged VM declarations because the cluster-wide Proxmox firewall default-drop blocked first-boot reachability before staged guest-network-policy automation existed
