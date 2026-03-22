# Configure Docker Runtime Runbook

## Purpose

This runbook captures the executable path for converging the production Docker baseline on `docker-runtime-lv3`.

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
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'docker version'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'docker compose version'
```

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'sudo cat /etc/docker/daemon.json'
```

## Notes

- This workstream intentionally does not define Docker guest firewall rules. That belongs to ADR 0023.
- This workstream intentionally does not define application stack layout or systemd-managed compose projects. That belongs to ADR 0024.
