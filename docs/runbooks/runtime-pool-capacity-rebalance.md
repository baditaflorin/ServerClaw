# Runtime Pool Capacity Rebalance

## Purpose

This runbook rebalances the existing production guest memory allocations that
fund the remaining runtime-pool rollout from ADR 0319 and keep the ADR 0321
host free-memory floor intact before `runtime-general-lv3` and
`runtime-control-lv3` come online.

## Result

- `docker-build-lv3` runs at `12 GiB`
- `artifact-cache-lv3` runs at `4 GiB`
- `coolify-lv3` runs at `6 GiB`
- `docker-runtime-lv3` runs at `18 GiB`
- the Proxmox host regains the headroom needed to create `runtime-general-lv3`
  and `runtime-control-lv3` without a one-way memory squeeze

## Commands

Syntax-check the rebalance playbook:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_CONFIG=ansible.cfg ansible-playbook --syntax-check -i inventory/hosts.yml playbooks/runtime-pool-capacity-rebalance.yml -e env=production
```

Run the guarded production live apply:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=runtime-pool-capacity-rebalance env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Replay the playbook directly when investigating the rebalance in isolation:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/runtime-pool-capacity-rebalance.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e env=production \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Verification

Verify the live Proxmox memory settings:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml proxmox_hosts -m shell \
  -a 'for id in 120 130 170 180; do echo === $id ===; qm config $id | egrep "^(name|memory):"; done' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the rebalanced guests came back with Docker:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-build-lv3,artifact-cache-lv3,coolify-lv3,docker-runtime-lv3 -m shell \
  -a 'hostname -s && systemctl is-active docker.service' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the host memory summary after the rebalance:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml proxmox_hosts -m shell \
  -a 'free -h' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operating Notes

- This rebalance is an enabling step for the remaining runtime-pool live apply,
  not a standalone capacity optimization project.
- The selected guests are intentionally restarted through Proxmox so the new
  `qm set --memory` values take effect immediately and leave a clean receipt.
- Do not widen the rebalance to unrelated guests during the same window unless
  the exact-main workstream explicitly owns the matching inventory and capacity
  updates.
