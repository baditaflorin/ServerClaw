# ADR 0045: Control-Plane Communication Lanes

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The system needs a coherent way for humans, services, and agents to communicate with the server through:

- secure commands
- email send
- API access
- internal event callbacks

Today those paths exist in pieces, but the boundaries between them are still implicit.

## Decision

We will standardize on four control-plane communication lanes.

### 1. Command Lane

- purpose: shell-level administration and repair
- transport: SSH only
- network path: Tailscale or private LV3 networks only
- identity: named human or agent identities using approved credentials
- access level: `ops` plus explicit `sudo`, not routine direct `root`

### 2. API Lane

- purpose: service control, automation endpoints, and management APIs
- transport: HTTPS only
- identity: scoped tokens, client certificates, or other approved machine auth
- network path: private-first, with explicit publication rules under the API publication ADR

### 3. Message Lane

- purpose: outbound transactional mail and operator notifications
- transport: authenticated submission to the internal mail platform
- identity: dedicated sender profiles, not shared global SMTP credentials
- network path: private submission to the chosen mail stack

### 4. Event Lane

- purpose: webhooks, callbacks, and asynchronous automation triggers
- transport: signed HTTP requests over private or explicitly published endpoints
- identity: scoped webhook secrets, signatures, or client certificates
- sinks: Windmill, monitoring, or other approved internal consumers

## Consequences

- Secure commands, API access, and mail send stop being vague capabilities and become explicit platform lanes.
- Each lane can be governed with different credentials, rate limits, audit expectations, and publication rules.
- Future apps must declare which lane they use rather than inventing their own one-off control path.

## Implementation Notes

- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/control-plane-lanes.json) is now the canonical machine-readable catalog for the four lanes plus the currently governed command, API, message, and event surfaces.
- [scripts/control_plane_lanes.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_plane_lanes.py) validates the catalog against the workflow catalog and canonical service topology, and exposes inspection commands for operators and assistants.
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repository_data_models.py) now enforces the lane catalog through the standard repository validation gate.
- [docs/runbooks/control-plane-communication-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/control-plane-communication-lanes.md) records the operating procedure for inspecting and extending the lane model.
- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/README.md) now renders a generated control-plane lane summary from the canonical catalog.
- Live verification from `main` on 2026-03-22 confirmed the governed SSH command path, the private Proxmox and step-ca APIs, the internal mail submission and operator notification surfaces, and the Stalwart webhook sink that currently implements the event lane.
