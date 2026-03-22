# Workstream ADR 0024: Docker Guest Security Baseline

- ADR: [ADR 0024](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0024-docker-guest-security-baseline.md)
- Title: Docker guest security baseline
- Status: ready
- Branch: `codex/adr-0024-docker-security`
- Worktree: `../proxmox_florin_server-docker-security`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `docker-build-lv3`, `playbooks/docker-security.yml`, `roles/docker_guest_security`

## Scope

- codify Docker-aware host firewall policy
- codify Debian security update behavior for Docker guests
- codify Docker socket access and local operator privilege rules
- separate runtime-host and build-host exceptions cleanly

## Non-Goals

- Docker package installation
- compose stack deployment layout
- public ingress publication

## Expected Repo Surfaces

- `playbooks/docker-security.yml`
- `roles/docker_guest_security/`
- `inventory/vars/docker_security.yml`
- `docs/runbooks/harden-docker-guests.md`
- `docs/adr/0024-docker-guest-security-baseline.md`
- `docs/workstreams/adr-0024-docker-security.md`
- `workstreams.yaml`

## Expected Live Surfaces

- VM `120`
- VM `130`
- Docker-aware host firewall rules
- guest patching and reboot policy

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/docker-security.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@65.108.75.123 ops@10.10.10.20 'sudo iptables -S DOCKER-USER || true'`

## Merge Criteria

- Docker guest hardening is automated and documented
- runtime and build exceptions are explicit
- the workstream registry and document are current

## Notes For The Next Assistant

- keep Docker firewall behavior explicit; do not rely on undocumented distro defaults
- if host firewall tooling is introduced, prove it works with Docker's packet path before merging
