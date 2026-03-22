# Workstream ADR 0052: Centralized Log Aggregation With Grafana Loki

- ADR: [ADR 0052](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md)
- Title: Centralized operational log search in Grafana
- Status: ready
- Branch: `codex/adr-0052-loki-logs`
- Worktree: `../proxmox_florin_server-loki-logs`
- Owner: codex
- Depends On: `adr-0011-monitoring`
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, Grafana, host logs, guest logs, container logs

## Scope

- choose Loki as the central log plane
- define log collection targets, labels, and retention boundaries
- keep log search aligned with the existing monitoring surface

## Non-Goals

- full live rollout in this planning workstream
- replacing structured receipts with log retention

## Expected Repo Surfaces

- `docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md`
- `docs/workstreams/adr-0052-loki-logs.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Loki integrated with Grafana on the monitoring plane
- governed log collection from host, guests, and runtime components

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md`

## Merge Criteria

- the ADR defines one central log plane and its boundaries clearly
- repo-first logging rules remain explicit

## Notes For The Next Assistant

- keep the first rollout inside the existing monitoring footprint if possible
