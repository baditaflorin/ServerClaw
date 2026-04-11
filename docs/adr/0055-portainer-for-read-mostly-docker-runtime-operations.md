# ADR 0055: Portainer For Read-Mostly Docker Runtime Operations

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.56.0
- Implemented In Platform Version: 0.30.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The Docker runtime VM is intentionally repo-managed, but there is still no visual console for:

- container health and restart state
- stack status at a glance
- container logs during triage
- bounded emergency actions such as restart or scale-down

Raw Docker CLI access remains useful, but it is not the best default experience for humans or agents that need quick runtime inspection.

## Decision

We will use Portainer as the private read-mostly operations console for the Docker runtime boundary.

Steady-state expectations:

1. Portainer is used primarily for inspection, logs, health, and bounded runtime actions.
2. Compose files and repo automation remain the source of truth for desired state.
3. UI-authored stack drift is treated as an exception path and must be documented immediately if used.
4. Human interactive access remains private-only, and machine access is constrained to the repo-managed Portainer wrapper instead of broad Docker shell access.

Initial scope:

- `docker-runtime`
- repo-managed Compose stacks
- container logs and restart history
- emergency restart and pause operations for approved identities

## Consequences

- Operators gain a visual runtime console without abandoning the repo-first delivery model.
- Agents can query or invoke narrow runtime actions through a governed surface instead of broad Docker shell access.
- Runtime drift risk increases if Portainer permissions are too broad.
- Role design and evidence expectations need to be explicit before live rollout.

## Boundaries

- Portainer must not become the primary place where stacks are designed or edited.
- Break-glass UI changes do not replace receipts, runbooks, or repo changes.
- Administrative publication follows the private-first API and operator-surface rules.

## Sources

- [Accessing the Portainer API](https://docs.portainer.io/api/access)
- [API documentation](https://docs.portainer.io/api/docs)
- [Docker roles and permissions](https://docs.portainer.io/advanced/docker-roles-and-permissions)

## Implementation Notes

- Portainer CE is now deployed privately on `docker-runtime` through [playbooks/portainer.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/portainer.yml) and [roles/portainer_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/portainer_runtime).
- The Proxmox host now publishes the Portainer UI and API only on the Tailscale path `https://100.118.189.95:9444` through the repo-managed host TCP proxy surface.
- Controller-local bootstrap material is now mirrored under `.local/portainer/` and consumed by the governed wrapper in [scripts/portainer_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/portainer_tool.py).
- Read-mostly inspection and bounded restart actions are now verified through the repo-managed wrapper and command catalog rather than by handing agents unrestricted Docker shell access.
