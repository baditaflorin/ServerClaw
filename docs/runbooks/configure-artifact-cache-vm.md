# Configure Artifact Cache VM

## Purpose

This runbook captures the dedicated ADR 0296 runtime: provision
`artifact-cache` as VM `180`, converge the private cache-plane runtime on
that guest, and then repoint the build host to consume the new cache plane.

## Model Summary

- create `artifact-cache` as VM `180` on `10.10.10.80`
- run the repo-managed pull-through cache plane on the guest
- keep the cache plane internal-only with no public NGINX publication
- move build and CI consumers first by rewiring `docker-build`

## Commands

Provision and converge the dedicated cache guest:

```bash
make configure-artifact-cache-vm
```

Then replay the build-host consumer adoption:

```bash
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache \
  env=production EXTRA_ARGS='-e bypass_promotion=true'
```

## What The Workflow Does

1. Ensures the Proxmox host has the `artifact-cache` guest defined as VM `180`.
2. Applies the repo-managed CPU, memory, disk, MAC, tags, and cloud-init network settings.
3. Performs a Proxmox stop/start cycle so the cloud-init-backed guest config is active.
4. Waits for SSH on `artifact-cache`.
5. Converges the guest firewall, named `ops` access, Docker runtime, and artifact-cache containers.
6. Configures Docker on `artifact-cache` to trust its own internal
   `10.10.10.80:5001-5004` cache listeners as insecure HTTP registries so the
   warm-set replay can seed the mirrors locally.
7. Renders `/opt/artifact-cache/seed-plan.json` on the guest and warms the repo-derived image set.
8. Replays the governed `build-artifact-cache` service so `docker-build` uses the new cache host and drops the old local cache stack.

## Verification

Verify the VM exists and is running:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo qm list | grep 180'
```

Verify the dedicated cache listeners and seed plan on the guest:

```bash
ansible -i inventory/hosts.yml artifact-cache -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.80:${port}/v2/" >/dev/null; done && jq ".seed_images | length" /opt/artifact-cache/seed-plan.json' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the build host now consumes the dedicated cache plane:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'docker buildx inspect lv3-cache --bootstrap >/dev/null && sudo cat /etc/docker/daemon.json && ! docker ps --format "{{.Names}}" | grep -q "^artifact-cache-"' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operational Notes

- Do not publish `artifact-cache` through the public edge.
- If the dedicated VM is unhealthy, roll the build host back to direct upstream
  access or the previous cache path before retrying the migration.
- Treat the VM MAC as part of the guest identity and keep it stable across reruns.

## Lessons Learned

- After changing `net0`, `ipconfig0`, or `cicustom`, run `qm cloudinit update <vmid>` before restarting the guest so the attached cloud-init seed reflects the new values.
- During first boot or early bootstrap, prefer a Proxmox-side stop/start cycle over `qm reboot` when the guest agent may not be available yet.
