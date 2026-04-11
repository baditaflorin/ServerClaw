# Configure Semaphore

## Purpose

This runbook defines the repo-managed Semaphore runtime for private Ansible job management on `runtime-control`.

Semaphore is private-only on this platform. Repository automation remains the source of truth; Semaphore provides a bounded UI and API for running repo-managed jobs.

## Canonical Surfaces

- playbook: [playbooks/semaphore.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/semaphore.yml)
- roles: [roles/semaphore_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/semaphore_postgres) and [roles/semaphore_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/semaphore_runtime)
- bootstrap helper: [scripts/semaphore_bootstrap.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/semaphore_bootstrap.py)
- governed wrapper: [scripts/semaphore_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/semaphore_tool.py)
- controller-local auth artifacts: `.local/semaphore/`

## Access Model

- Semaphore is published only through the Proxmox host Tailscale proxy at `http://100.118.189.95:8020`
- the controller-local bootstrap artifacts are mirrored under `.local/semaphore/`
- the seeded project uses a repo-staged local checkout and the `Semaphore Self-Test` template to verify the Ansible job path
- broader infrastructure jobs stay repo-managed and must be added deliberately with explicit inventory and secret boundaries

## Primary Commands

Syntax-check the workflow:

```bash
make syntax-check-semaphore
```

Converge Semaphore live:

```bash
make converge-semaphore
```

List Semaphore projects:

```bash
make semaphore-manage ACTION=list-projects
```

List templates in the seeded project:

```bash
make semaphore-manage ACTION=list-templates SEMAPHORE_ARGS='--project "LV3 Semaphore"'
```

Run the seeded self-test template and wait for completion:

```bash
make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'
```

Read task output for one run:

```bash
make semaphore-manage ACTION=task-output SEMAPHORE_ARGS='--task-id 1'
```

## Verification

After a converge:

1. `make syntax-check-semaphore`
2. `curl -fsS http://100.118.189.95:8020/api/ping`
3. `make semaphore-manage ACTION=list-projects`
4. `make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'`
5. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.92 'docker compose --file /opt/semaphore/docker-compose.yml ps && sudo ls -l /run/lv3-secrets/semaphore /srv/proxmox-host_server-semaphore'`

## Operating Rules

- keep Semaphore private-only
- use the seeded project and governed CLI wrapper to verify API and job-runner health
- treat new inventories, SSH credentials, and broader infrastructure templates as explicit follow-up work, not implicit bootstrap scope
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn
