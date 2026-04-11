# Workstream: naughty-jepsen Operational Fixes

- ADR: [ADR 0043](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md)
- Title: OpenBao unseal watcher, Keycloak VM migration, oauth2-proxy fix
- Status: in_progress
- Branch: `claude/naughty-jepsen`
- Worktree: `.claude/worktrees/naughty-jepsen`
- Owner: claude
- Depends On: `adr-0043-openbao-for-secrets-transit-and-dynamic-credentials`, `adr-0056-keycloak-for-operator-and-agent-sso`
- Conflicts With: none

## Scope

- Replace oneshot boot-time OpenBao unseal with a persistent event-driven watcher service
- Correct Keycloak owning VM from `docker-runtime` to `runtime-control` across all catalog and topology files
- Fix oauth2-proxy internal Keycloak URLs to point at `runtime-control`
- Fix dozzle-agent healthcheck (scratch image cannot run shell-based checks)
- Register capacity-model entries for new VMs introduced by parallel ADR work

## Non-Goals

- Keycloak clustering or JGroups configuration changes
- OpenBao TLS certificate management
- Any changes to service secrets or AppRole credentials
