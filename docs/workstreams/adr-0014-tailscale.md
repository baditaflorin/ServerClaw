# Workstream ADR 0014: Tailscale Private Access Rollout

- ADR: [ADR 0014](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0014-operator-access-to-private-guest-network.md)
- Title: Tailscale private guest access
- Status: merged
- Branch: `codex/adr-0014-tailscale`
- Worktree: `../proxmox_florin_server-tailscale`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: Proxmox host access, guest SSH reachability, private `10.10.10.0/24` routing

## Scope

- install and configure Tailscale in the chosen access position
- make operator access to the private guest network predictable
- document the steady-state path for reaching `10.10.10.30`

## Non-Goals

- monitoring rollout
- public ingress changes
- backup storage changes

## Expected Repo Surfaces

- `roles/` for Tailscale or access automation
- `inventory/`
- `docs/runbooks/`
- `docs/adr/0014-operator-access-to-private-guest-network.md`

## Expected Live Surfaces

- Proxmox host and/or dedicated access VM
- guest SSH access path
- operator laptop onboarding procedure

## Verification

- operator can reach at least one private guest over the intended Tailscale path
- old jump-host-only path is either retained as break-glass or explicitly deprecated

## Current Implementation Notes

- the Proxmox host is the selected steady-state Tailscale subnet router for `10.10.10.0/24`
- guest inventory now defaults to direct private-IP access and can be forced back to `ProxyJump` with `proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `10.10.10.30` is the primary operator verification target
- the runbook documents operator onboarding, route approval, and break-glass fallback

## Repo Changes In This Workstream

- add `roles/proxmox_tailscale/` for host-side Tailscale install and subnet-router convergence
- add `make configure-tailscale`
- add `docs/runbooks/configure-tailscale-access.md`
- update ADR 0014 with the chosen termination point and fallback model
- update guest SSH inventory defaults so Tailscale is the normal path

## Remaining Live Blockers

- the host is installed with Tailscale but still in `NeedsLogin`
- the host still needs to be attached to the tailnet with a valid auth flow
- the route `10.10.10.0/24` still needs tailnet approval unless auto-approval is configured
- post-apply verification still needs to be recorded after the change is applied from `main`

## Merge Criteria

- automation is idempotent
- access policy and verification are documented
- workstream status is updated in `workstreams.yaml`

## Notes For The Next Assistant

- avoid mixing host firewall redesign into this workstream unless required
- do not update `platform_version` until merged work has been applied live from `main`
- this workstream is merged to `main` but not yet applied live
