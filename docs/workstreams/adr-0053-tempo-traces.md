# Workstream ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo

- ADR: [ADR 0053](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md)
- Title: Distributed tracing and service maps for internal apps and workflows
- Status: ready
- Branch: `codex/adr-0053-tempo-traces`
- Worktree: `../proxmox_florin_server-tempo-traces`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0052-loki-logs`
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, Grafana, internal APIs, workflow execution

## Scope

- choose Tempo and OpenTelemetry for trace collection
- define naming, collector, and first-instrumentation boundaries
- align traces with the existing Grafana monitoring model

## Non-Goals

- tracing every service before the first implementation
- public publication of internal tracing endpoints

## Expected Repo Surfaces

- `docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md`
- `docs/workstreams/adr-0053-tempo-traces.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Tempo integrated into the monitoring plane
- trace collection for selected control-plane and internal app paths

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md`

## Merge Criteria

- the ADR defines trace ownership, collector boundaries, and first targets
- service-map value is explicit rather than implied

## Notes For The Next Assistant

- prioritize instrumentation where workflows cross several internal services
