# ADR 0049: Private-First API Publication Model

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.50.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform is adding more APIs:

- Proxmox API
- mail platform API
- future secret authority API
- workflow runtime API

Without a publication policy, those APIs will drift toward accidental exposure.

## Decision

Every API must be classified into one of three publication tiers.

### 1. Internal-Only

- reachable only from LV3 private networks or trusted control-plane hosts
- examples: OpenBao, `step-ca`, internal webhook endpoints

### 2. Operator-Only

- reachable from approved operator devices over private access
- examples: Proxmox management, Windmill admin surface

### 3. Public Edge

- intentionally published on a public domain through the edge model
- requires explicit ADR or implementation approval
- examples: public application APIs, not internal admin APIs

Default rule:

- if a new API is not explicitly classified, it is internal-only

## Consequences

- New apps cannot quietly expose administrative ports just because they listen on HTTPS.
- Publication becomes a design decision, not an implementation accident.
- The public edge stays focused on deliberately published services instead of becoming a spillover path for internal control planes.

## Implementation Notes

- [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/api-publication.json) is now the canonical machine-readable catalog for the three publication tiers plus the currently classified Proxmox, `step-ca`, OpenBao, Windmill, mail-gateway, and webhook surfaces.
- [scripts/api_publication.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/api_publication.py) validates the publication catalog, verifies that every governed API or event HTTP surface is classified, and exposes inspection commands for operators and assistants.
- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/control-plane-lanes.json) now includes the live OpenBao and Windmill APIs so the governed lane inventory matches the current private control-plane reality.
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repository_data_models.py) now fails validation if a governed API or webhook surface is missing an ADR 0049 publication tier.
- [docs/runbooks/private-first-api-publication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/private-first-api-publication.md) records the operating procedure for inspecting and extending the publication model.
- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/README.md) now renders the publication tiers and classified HTTP surfaces from canonical repo state.
