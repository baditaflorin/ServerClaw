# Workstream ADR 0025: Compose-Managed Runtime Stacks

- ADR: [ADR 0025](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0025-compose-managed-runtime-stacks.md)
- Title: Compose-managed runtime stacks
- Status: ready
- Branch: `codex/adr-0025-docker-compose-stacks`
- Worktree: `../proxmox-host_server-docker-compose-stacks`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `docker-runtime`, `playbooks/docker-compose-stacks.yml`, `roles/docker_compose_stack`, `/srv`

## Scope

- codify how long-running compose stacks are laid out on the runtime VM
- add a systemd-managed lifecycle for compose projects
- document deployment, rollback, and health verification requirements per stack

## Non-Goals

- Docker guest firewall policy
- Docker package installation
- build-host workflows

## Expected Repo Surfaces

- `playbooks/docker-compose-stacks.yml`
- `roles/docker_compose_stack/`
- `inventory/vars/docker_compose_stacks.yml`
- `docs/runbooks/deploy-docker-compose-stack.md`
- `docs/adr/0025-compose-managed-runtime-stacks.md`
- `docs/workstreams/adr-0025-docker-compose-stacks.md`
- `workstreams.yaml`

## Expected Live Surfaces

- VM `120`
- `/srv/<stack>/`
- systemd units for compose-managed stacks

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/docker-compose-stacks.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@203.0.113.1 ops@10.10.10.20 'systemctl list-unit-files | grep docker-compose || true'`

## Merge Criteria

- compose stack lifecycle is automated and documented
- stack layout is explicit and repeatable
- the workstream registry and document are current

## Notes For The Next Assistant

- keep public exposure aligned with ADR 0021; port publication is not publication policy
- make each stack bring its own runbook and rollback path
