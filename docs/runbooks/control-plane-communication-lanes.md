# Control-Plane Communication Lanes

## Purpose

This runbook defines the canonical repository contract for ADR 0045.

Use it when you need to:

- inspect the approved command, API, message, and event lanes
- register a new control-plane surface
- verify that a proposed change fits an existing lane instead of creating an ad hoc path

## Canonical Sources

- lane catalog: [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/control-plane-lanes.json)
- lane CLI and validator: [scripts/control_plane_lanes.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_plane_lanes.py)
- API publication catalog: [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/api-publication.json)
- service inventory cross-checks: [inventory/host_vars/proxmox-host.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml)
- workflow cross-checks: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)
- architecture decision: [docs/adr/0045-control-plane-communication-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0045-control-plane-communication-lanes.md)
- publication policy: [docs/runbooks/private-first-api-publication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/private-first-api-publication.md)

## Lane Summary

1. `command`
   - SSH-only command and repair access
   - steady-state target is `ops`, with explicit `sudo`
   - current governed paths are host Tailscale SSH and guest SSH through the Proxmox jump path
2. `api`
   - private-first management and service APIs
   - current governed paths are the Proxmox, `step-ca`, OpenBao, Windmill, and internal mail gateway APIs
3. `message`
   - outbound transactional mail and operator notifications
   - current governed paths are internal SMTP submission on the mail platform and the named Proxmox notification endpoint
4. `event`
   - webhook-style callbacks and asynchronous automation/event sinks
   - current governed path is the Stalwart-to-mail-gateway webhook used for telemetry and downstream automation

## Inspection Commands

- list lanes: `python scripts/control_plane_lanes.py --list`
- show one lane: `python scripts/control_plane_lanes.py --lane api`
- validate the catalog directly: `python scripts/control_plane_lanes.py --validate`
- inspect the publication tiers for those HTTP surfaces: `python scripts/api_publication.py --list`
- validate through the standard repo gate: `make validate-data-models`

## Change Procedure

When adding or changing a control-plane surface:

1. choose one existing lane or justify a new architectural decision
2. update [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/control-plane-lanes.json)
3. classify any HTTP API or webhook in [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/api-publication.json)
4. update the owning runbook and workflow or service docs if the surface changed operationally
5. run `python scripts/control_plane_lanes.py --validate`
6. run `python scripts/api_publication.py --validate`
7. run `make validate-data-models`
8. run `make generate-status-docs` if the README lane summary changed

## Review Rules

- do not introduce a new control-plane endpoint without placing it in one lane
- do not introduce an HTTP API or callback without assigning an ADR 0049 publication tier
- do not reuse the message lane for arbitrary callbacks or the event lane for privileged shell execution
- prefer existing private paths before introducing new public publication
- keep service refs and workflow refs aligned with the canonical catalogs instead of copying free-form labels
