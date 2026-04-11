# Repair Guest Netplan MAC Drift

## Purpose

This runbook repairs a Debian guest whose netplan cloud-init file still matches an old virtual NIC MAC address after the Proxmox VM config now presents a different MAC.

When this happens, the guest still boots, but the primary NIC stays down and the host sees `Destination Host Unreachable` for the guest IP.

## Observed Case

On 2026-03-22 this affected all four initial guests:

- `110` `nginx-edge`
- `120` `docker-runtime`
- `130` `docker-build`
- `140` `monitoring`

Symptom pattern:

- `qm status <vmid>` still reports `running`
- `qm guest exec <vmid> -- ip link` shows `ens18` present but down
- `/etc/netplan/50-cloud-init.yaml` matches a different MAC than `qm config <vmid>` reports in `net0`

## Repair Flow

Read the current MAC from Proxmox:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 \
  'sudo qm config 120 | sed -n "s/^net0: virtio=\([^,]*\),.*/\1/p"'
```

Inspect the guest-side netplan file through the QEMU guest agent:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 \
  'sudo qm guest exec 120 -- cat /etc/netplan/50-cloud-init.yaml'
```

If the MACs differ, update the guest file and reapply netplan:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 \
  'sudo qm guest exec 120 -- /bin/sh -lc '\''sed -i "s/OLD-MAC/NEW-MAC/" /etc/netplan/50-cloud-init.yaml && netplan apply && ip -4 addr show eth0'\'''
```

## Verification

Verify reachability from the Proxmox host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 \
  'ping -c 1 10.10.10.20'
```

Verify the guest IP is back on `eth0`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 \
  'sudo qm guest exec 120 -- ip -4 addr show eth0'
```

## Notes

- This is a live repair, not a substitute for root-cause analysis.
- If the MAC drift reappears, create a dedicated follow-up workstream to trace why the Proxmox guest `net0` MACs differ from the guest-side netplan files.
- During the 2026-03-22 Docker build telemetry rollout, VMs `110`, `120`, `130`, and `140` all needed this repair again before the SSH jump path for monitoring convergence worked.
