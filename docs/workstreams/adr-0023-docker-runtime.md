# Workstream ADR 0023: Docker Runtime VM Baseline

- ADR: [ADR 0023](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0023-docker-runtime-vm-baseline.md)
- Title: Docker runtime VM baseline
- Status: live_applied
- Branch: `codex/adr-0023-docker-runtime`
- Worktree: `../proxmox_florin_server-docker-runtime`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `playbooks/docker-runtime.yml`, `roles/docker_runtime`

## Scope

- install Docker Engine from Docker's official Debian repository on `docker-runtime-lv3`
- replace conflicting distro Docker packages when present
- install the Compose v2 plugin
- configure Docker daemon defaults for service continuity and bounded log growth
- document the operator convergence and verification path

## Non-Goals

- Docker guest firewall hardening
- build-host tuning
- app-specific compose stacks
- public publication of runtime services

## Expected Repo Surfaces

- `playbooks/docker-runtime.yml`
- `roles/docker_runtime/`
- `Makefile`
- `docs/runbooks/configure-docker-runtime.md`
- `docs/adr/0023-docker-runtime-vm-baseline.md`
- `docs/workstreams/adr-0023-docker-runtime.md`
- `workstreams.yaml`

## Expected Live Surfaces

- VM `120`
- `/etc/apt/sources.list.d/docker.sources`
- `/etc/docker/daemon.json`
- `docker` systemd service

## Verification

- `make syntax-check-docker-runtime`
- `make converge-docker-runtime`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker version && docker compose version && sudo cat /etc/docker/daemon.json'`

## Merge Criteria

- Docker runtime automation is idempotent
- the operator runbook is current
- the workstream registry and document are current
- no protected integration files are changed on this branch

## Notes For The Next Assistant

- keep this workstream limited to the runtime host baseline
- move firewall policy into ADR 0024 instead of expanding this role ad hoc
- move stack/systemd deployment behavior into ADR 0025 instead of embedding application assumptions here
- this workstream is merged to `main` and applied live
- live rollout required one manual recovery step because VM `120` had a stale netplan MAC match; that procedure is documented in the Docker runtime runbook
