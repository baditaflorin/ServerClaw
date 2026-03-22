# Workstream ADR 0071: Agent Observation Loop And Autonomous Drift Detection

- ADR: [ADR 0071](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0071-agent-observation-loop-and-drift-detection.md)
- Title: Scheduled proactive drift detection with structured findings and governed self-healing
- Status: merged
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

- `python3 -m py_compile scripts/platform_observation_tool.py tests/test_platform_observation_tool.py scripts/control_plane_lanes.py scripts/validate_repository_data_models.py`
- `uvx --from pytest --with pyyaml python -m pytest tests/test_platform_observation_tool.py -q`
- `uvx --from pyyaml python scripts/validate_repository_data_models.py --validate`
- `ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local ANSIBLE_REMOTE_TEMP=/tmp ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check`
- `uvx --from pyyaml python scripts/platform_observation_tool.py`

## Merge Criteria

- all six checks are implemented and produce valid finding JSON
- the finding schema is valid JSON Schema
- at least one controller observation cycle has been run against the live platform and written to `.local/platform-observation/latest/`
- the dead-man contract is documented for both artifact staleness and NATS event staleness, even though live alert activation remains pending

## Merge Notes

- Repository implementation completed on `2026-03-23` for release `0.59.0`.
- The current execution surface is controller-local. Windmill receives repo-managed disabled placeholders for the observation loop and daily digest, but the schedules are intentionally not enabled yet.
- A live observation run confirmed that the tooling works end-to-end and also surfaced current drift: several controller-side health probes timed out, tracked images are mostly unpinned, `step-ca` and OpenBao proxy certificates expire on `2026-03-23`, and only VM `110` currently has a recent PBS recovery point.
