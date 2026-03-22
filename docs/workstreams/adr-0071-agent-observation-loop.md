# Workstream ADR 0071: Agent Observation Loop And Autonomous Drift Detection

- ADR: [ADR 0071](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0071-agent-observation-loop-and-drift-detection.md)
- Title: Scheduled proactive drift detection with structured findings and governed self-healing
- Status: ready
- Branch: `codex/adr-0071-agent-observation-loop`
- Worktree: `../proxmox_florin_server-agent-observation-loop`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0057-mattermost-chatops`, `adr-0058-nats-event-bus`, `adr-0061-glitchtip-failure-signals`, `adr-0064-health-probe-contracts`, `adr-0065-secret-rotation-automation`, `adr-0068-container-image-policy`
- Conflicts With: none
- Shared Surfaces: Windmill workflows, NATS subjects, Mattermost `#platform-findings`, GlitchTip, Open WebUI dashboard

## Scope

- create Windmill workflow `platform-observation-loop` with 4-hour schedule
- implement the six named checks: vm-state, service-health, image-freshness, secret-ages, certificate-expiry, backup-recency
- define finding JSON schema in `docs/schema/platform-finding.json`
- wire findings to NATS `platform.findings.<check-name>` and Mattermost `#platform-findings`
- add dead-man's switch: alert if no finding events arrive within 5 hours
- document the observation model in `docs/runbooks/agent-observation-loop.md`
- integrate finding stream into Open WebUI daily digest

## Non-Goals

- autonomous remediation beyond pre-approved self-healing commands in the first iteration
- security-specific vulnerability scanning (separate concern)

## Expected Repo Surfaces

- Windmill workflow definition for `platform-observation-loop`
- `docs/schema/platform-finding.json`
- `docs/runbooks/agent-observation-loop.md`
- NATS subject definitions added to `config/control-plane-lanes.json`
- `docs/adr/0071-agent-observation-loop-and-drift-detection.md`
- `docs/workstreams/adr-0071-agent-observation-loop.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill workflow running on 4-hour schedule
- NATS subject `platform.findings.*` receiving structured finding events
- Mattermost `#platform-findings` channel receiving non-ok findings
- dead-man's switch alert configured in Grafana or Uptime Kuma

## Verification

- manually trigger `platform-observation-loop` and verify all six checks produce a finding event
- verify a non-ok finding appears in Mattermost within 30 seconds of emission
- stop the workflow schedule and verify dead-man's switch fires within 5 hours

## Merge Criteria

- all six checks are implemented and produce valid finding JSON
- the finding schema is valid JSON Schema
- at least one finding cycle has been run against the live platform with a receipt
- the dead-man's switch is configured and documented

## Notes For The Next Assistant

- implement checks in order of read-only safety: vm-state and service-health first, then image-freshness and certificate-expiry
- the maintenance-window suppression mechanism can be a simple NATS KV flag checked at the start of each finding emission
