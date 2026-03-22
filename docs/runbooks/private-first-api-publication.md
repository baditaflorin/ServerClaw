# Private-First API Publication

## Purpose

This runbook defines the canonical repository contract for ADR 0049.

Use it when you need to:

- inspect the approved publication tiers for APIs and HTTP callbacks
- classify a new private or public API surface
- verify that an administrative endpoint is not drifting onto the public edge by accident

## Canonical Sources

- publication catalog: [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/api-publication.json)
- publication CLI and validator: [scripts/api_publication.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/api_publication.py)
- lane catalog cross-checks: [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json)
- service inventory cross-checks: [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- architecture decision: [docs/adr/0049-private-first-api-publication-model.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0049-private-first-api-publication-model.md)

## Tier Summary

1. `internal-only`
   - default tier for new APIs and HTTP callbacks
   - reachable only from LV3 private networks, loopback listeners, or explicitly trusted control-plane hosts
   - examples on the current platform are `step-ca`, OpenBao, the mail gateway, and the Stalwart event webhook
2. `operator-only`
   - reachable only from approved operator devices over private access such as Tailscale
   - examples on the current platform are the Proxmox API and Windmill
3. `public-edge`
   - intentionally published on a public hostname through the edge model
   - requires explicit ADR or approved implementation evidence before it is allowed

## Inspection Commands

- list tiers and classified surfaces: `python scripts/api_publication.py --list`
- show one surface: `python scripts/api_publication.py --surface proxmox-management-api`
- validate the catalog directly: `python scripts/api_publication.py --validate`
- validate through the standard repo gate: `make validate-data-models`

## Change Procedure

When adding or changing an API or webhook surface:

1. register the HTTP surface in [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json) if it is part of the governed control plane
2. classify the surface in [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/api-publication.json)
3. keep the default tier as `internal-only` unless there is a clear operator-only or public-edge reason
4. if the surface is `public-edge`, declare the intended public hostname and capture the approval path in the relevant ADR or workstream
5. update the owning runbook, workflow metadata, or service docs if the operational path changed
6. run `python scripts/api_publication.py --validate`
7. run `make validate-data-models`
8. run `make generate-status-docs` if the README publication summary changed

## Review Rules

- do not assume HTTPS means public publication is acceptable
- do not leave a new API or webhook unclassified
- do not publish operator or internal admin surfaces through the public NGINX edge without an explicit ADR or approved implementation record
- keep the classification aligned with the lane catalog and service inventory instead of duplicating conflicting endpoint details
