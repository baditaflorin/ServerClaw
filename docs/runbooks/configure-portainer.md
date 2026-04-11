# Configure Portainer

## Purpose

This runbook defines the repo-managed Portainer runtime for read-mostly Docker operations on `docker-runtime`.

Portainer is private-only on this platform. Desired state remains in git and Compose files; Portainer is the visual inspection and bounded runtime-action surface.

## Canonical Surfaces

- playbook: [playbooks/portainer.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/portainer.yml)
- role: [roles/portainer_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/portainer_runtime)
- governed wrapper: [scripts/portainer_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/portainer_tool.py)
- workflow metadata: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
- command metadata: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/command-catalog.json)
- controller-local auth artifacts: `.local/portainer/`

## Access Model

- Portainer is published only through the Proxmox host Tailscale proxy at `https://100.118.189.95:9444`
- the controller-local bootstrap credential is mirrored under `.local/portainer/admin-auth.json`
- the governed machine surface is `make portainer-manage`, not arbitrary direct Docker CLI access
- UI-authored stack design or stack-file edits are out of bounds; document any emergency UI mutation immediately and bring it back to repo truth in the same turn

## Primary Commands

Syntax-check the workflow:

```bash
make syntax-check-portainer
```

Converge Portainer live:

```bash
make converge-portainer
```

List containers through the governed wrapper:

```bash
make portainer-manage ACTION=list-containers PORTAINER_ARGS='--all'
```

Read logs for one container:

```bash
make portainer-manage ACTION=container-logs PORTAINER_ARGS='--container portainer --tail 100'
```

Restart one container as an emergency action:

```bash
make portainer-manage ACTION=restart-container PORTAINER_ARGS='--container portainer'
```

## Verification

After a converge:

1. `make syntax-check-portainer`
2. `curl -sk https://100.118.189.95:9444/api/system/status`
3. `make portainer-manage ACTION=list-containers PORTAINER_ARGS='--all'`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/portainer/docker-compose.yml ps'`

## Operating Rules

- keep Portainer private-only
- use Portainer for inspection, logs, and bounded restart actions
- do not treat Portainer as the source of truth for stack definitions
- after any emergency restart, re-run the owning repo-managed converge path if drift or degraded health remains
