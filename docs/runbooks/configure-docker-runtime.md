# Configure Docker Runtime Runbook

## Purpose

This runbook captures the executable path for converging the production Docker baseline on `docker-runtime`.

## Result

- Docker Engine is installed from Docker's official Debian repository
- conflicting distro Docker packages are removed if present
- Docker Compose v2 is available through `docker compose`
- Docker daemon uses `live-restore`
- container JSON logs are rotated with bounded size and count
- `ops` is present in the local `docker` group

## Command

```bash
make converge-docker-runtime
```

## What the playbook does

1. Installs the apt prerequisites needed for Docker's repository.
2. Adds Docker's official Debian apt key and repository.
3. Removes conflicting packages such as `docker.io` when they exist.
4. Installs `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, and `docker-compose-plugin`.
5. Renders `/etc/docker/daemon.json` with the runtime baseline.
6. Enables and starts the Docker service.

## Verification

```bash
make syntax-check-docker-runtime
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker version'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose version'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'sudo cat /etc/docker/daemon.json'
```

## Notes

- Container-runtime hardening still belongs to ADR 0024, but guest-level network enforcement now comes from the shared ADR 0067 firewall policy.
- This workstream intentionally does not define application stack layout or systemd-managed compose projects. That belongs to ADR 0025.

## Recovery Note

During the live rollout on 2026-03-22, VM `120` became unreachable because `/etc/netplan/50-cloud-init.yaml` still matched an old guest NIC MAC address while Proxmox was presenting a newer one.

Observed symptom:

- `networkctl status ens18` showed the interface as unmanaged and down
- the Proxmox host returned `Destination Host Unreachable` for `10.10.10.20`

Manual recovery used for this rollout:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm config 120 | grep ^net0'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 "sudo qm guest exec 120 -- bash -lc 'sed -i \"s/<old-mac>/<current-mac>/\" /etc/netplan/50-cloud-init.yaml && netplan apply'"
```

If this recurs, treat it as guest network metadata drift and reconcile the guest's netplan MAC match before retrying the Docker convergence.
