# Workstream ADR 0041: Dockerized Mail Platform With API, Grafana Telemetry, And Failover Delivery

- ADR: [ADR 0041](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md)
- Title: Dockerized mail platform planning and decision record
- Status: merged
- Branch: `codex/adr-0040-email-platform`
- Worktree: `../proxmox-host_server-email-platform`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0023-docker-runtime`
- Conflicts With: none
- Shared Surfaces: `docker-runtime`, `monitoring`, mail DNS, SMTP publication, Stalwart management API, Grafana dashboards

## Scope

- define the first-class mail platform architecture for LV3
- choose an open-source implementation that fits Docker deployment, API automation, and Grafana observability requirements
- define the fallback delivery model for when the primary local mail path fails
- leave the repository with enough operational detail that another assistant can implement the platform without hidden chat context

## Non-Goals

- live deployment of the mail stack in this workstream
- publishing new DNS, MX, or PTR records in this workstream
- claiming that the platform is already ready for production mail delivery
- replacing the current notification sendmail endpoint before the new stack is implemented and verified

## Expected Repo Surfaces

- `docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md`
- `docs/runbooks/prepare-mail-platform-rollout.md`
- `docs/workstreams/adr-0041-email-platform.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a Stalwart mail stack on `docker-runtime`
- a stable local SMTP relay endpoint for LV3 services
- a failover relay path for deferred or failed outbound delivery
- a Grafana mail dashboard on `monitoring`
- scoped API credentials for service automation and agent automation

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/prepare-mail-platform-rollout.md`

## Merge Criteria

- the ADR names a recommended open-source stack and explains why it fits better than the alternatives considered
- the ADR defines mail flow, observability, API, and failover expectations concretely
- the rollout runbook documents implementation prerequisites and verification targets
- no protected release-state files are changed until the integration step

## Notes For The Next Assistant

- the recommended shape is Stalwart as the primary mail platform, with a small local relay tier to decouple application submission from the full mail stack
- this workstream is intentionally documentation-first; the next implementation workstream should split runtime stack, public SMTP ingress, DNS/rDNS, and Grafana dashboard work into reviewable steps
- do not claim live mail readiness until DNS, reverse DNS, reputation, anti-abuse controls, queue visibility, and backup delivery are all verified
- the implementation branch remained `codex/adr-0040-email-platform`, but the ADR and workstream were renumbered to `0041` during integration because `0040` was already assigned on `main`
