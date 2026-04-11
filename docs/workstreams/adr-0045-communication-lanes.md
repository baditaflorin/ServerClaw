# Workstream ADR 0045: Control-Plane Communication Lanes

- ADR: [ADR 0045](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0045-control-plane-communication-lanes.md)
- Title: Command, API, message, and event lane policy
- Status: live_applied
- Branch: `codex/adr-0045-communication-lanes`
- Worktree: `../proxmox-host_server-communication-lanes`
- Owner: codex
- Depends On: `adr-0014-tailscale`, `adr-0041-email-platform`
- Conflicts With: none
- Shared Surfaces: SSH, HTTPS APIs, SMTP submission, webhook flows

## Scope

- define the platform communication lanes
- map secure commands, email send, API access, and webhooks into explicit categories
- document the default transports and trust boundaries for each lane

## Non-Goals

- adding new public exposure by default

## Expected Repo Surfaces

- `docs/adr/0045-control-plane-communication-lanes.md`
- `docs/workstreams/adr-0045-communication-lanes.md`
- `config/control-plane-lanes.json`
- `scripts/control_plane_lanes.py`
- `docs/runbooks/control-plane-communication-lanes.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- step-ca-backed `ops` SSH on the Proxmox host and the governed Proxmox jump path to guests
- private-first control-plane APIs on the Proxmox host, step-ca, and the mail gateway
- internal mail submission and named Proxmox notification routing as the message lane
- the Stalwart webhook sink remaining explicit, private, and documented as the current event lane

## Verification

- `python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_plane_lanes.py --validate`
- `make -C /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server validate-data-models`
- `make -C /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server generate-status-docs`
- `curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt https://100.118.189.95:9443/health`
- issue a short-lived `ops` SSH certificate through `step-ca` and verify login to `ops@100.118.189.95` plus `ops@10.10.10.20`
- verify the Proxmox API version endpoint with the `lv3-automation@pve!primary` token and the private mail gateway health endpoint on `docker-runtime`

## Merge Criteria

- the ADR clearly maps each communication need into one lane
- the lane boundaries align with the current private-network-first model

## Live Apply Notes

- Live apply completed on `2026-03-22` from `main`.
- Verification confirmed the command lane through step-ca-backed `ops` SSH on the Proxmox host and through the governed jump path to `docker-runtime`.
- Verification confirmed the private API lane on `pveproxy`, `step-ca`, and the mail gateway, plus the message and event lanes on SMTP submission, Proxmox notifications, and `/webhooks/stalwart`.
