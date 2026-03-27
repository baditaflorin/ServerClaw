# Staging Environment

This runbook documents the repo-managed path for bringing up the Proxmox-hosted staging lane behind `vmbr20`.

## Purpose

Use staging when we need a real pre-production network segment for safe live-apply validation before touching production.

This runbook covers:

- the host bridge for the staging subnet
- the OpenTofu VM declarations already committed under `tofu/environments/staging/`
- the minimum checks needed before claiming staging is available

## Topology

- bridge: `vmbr20`
- gateway: `10.20.10.1/24`
- subnet: `10.20.10.0/24`
- current staged VM declarations:
  - `docker-runtime-staging-lv3` on `10.20.10.20`
  - `monitoring-staging-lv3` on `10.20.10.40`

The host advertises the staging subnet through Tailscale once the network role is applied from `main`.

## Host Bridge

Render and apply the staging bridge on the Proxmox host:

```bash
make configure-staging-bridge
```

Expected result:

- `/etc/network/interfaces` contains a managed `vmbr20` stanza
- `ip -brief addr show vmbr20` reports `10.20.10.1/24`
- the Tailscale route set includes `10.20.10.0/24`

## Stage The VMs

Review the staging plan:

```bash
make remote-tofu-plan ENV=staging
```

Apply only after review:

```bash
make remote-tofu-apply ENV=staging
```

## Safe Checks

Non-destructive checks after the bridge and VMs exist:

```bash
python3 scripts/integration_suite.py --mode gate --environment staging
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/services/grafana.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=staging -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check
```

If staging services publish active bindings in `config/service-capability-catalog.json`, the integration suite should switch from a structured `skipped` report to a real gate run automatically.

From `main`, the normal operator entrypoint remains `make live-apply-service service=grafana env=staging`. The direct `ansible-playbook --syntax-check` command above is the safer branch-local proof that the staged playbook path still parses before canonical-truth surfaces are regenerated at integration time.

## Live Readiness

Do not claim staging is live until all of the following are true:

- `vmbr20` exists on the Proxmox host
- at least one staged VM is present in Proxmox state
- the staged VM is reachable over SSH through the Proxmox jump path
- the relevant service catalog environment bindings are marked `active`
- at least one non-destructive staging gate has passed from `main`
