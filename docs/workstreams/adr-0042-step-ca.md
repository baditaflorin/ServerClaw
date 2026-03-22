# Workstream ADR 0042: step-ca For SSH And Internal TLS

- ADR: [ADR 0042](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md)
- Title: Internal certificate authority for SSH and private TLS
- Status: merged
- Branch: `codex/adr-0042-step-ca`
- Worktree: `../proxmox_florin_server-step-ca`
- Owner: codex
- Depends On: `adr-0014-tailscale`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, SSH trust, internal TLS

## Scope

- choose the internal CA app and trust model
- define SSH and X.509 boundaries for humans, agents, services, and hosts
- document the private-only publication and bootstrap expectations

## Non-Goals

- live deployment in this planning workstream
- replacing the current public Let's Encrypt edge

## Expected Repo Surfaces

- `docs/adr/0042-step-ca-for-ssh-and-internal-tls.md`
- `docs/workstreams/adr-0042-step-ca.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private `step-ca` deployment on `docker-runtime-lv3`
- SSH certificate trust on the Proxmox host and managed guests
- internal TLS issuance for private APIs

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md`

## Merge Criteria

- the ADR defines where SSH and X.509 issuance should live
- the workstream records the trusted surfaces and dependencies clearly

## Notes For The Next Assistant

- keep the first implementation private-only
- avoid mixing public edge work into the CA rollout
