# Workstream ADR 0014: Tailscale Private Access Rollout

- ADR: [ADR 0014](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0014-operator-access-to-private-guest-network.md)
- Title: Tailscale private guest access
- Status: ready
- Branch: `codex/adr-0014-tailscale`
- Worktree: `../proxmox_florin_server-tailscale`
- Owner: unassigned
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

## Merge Criteria

- automation is idempotent
- access policy and verification are documented
- workstream status is updated in `workstreams.yaml`

## Notes For The Next Assistant

- avoid mixing host firewall redesign into this workstream unless required
- do not update `platform_version` until merged work has been applied live from `main`
