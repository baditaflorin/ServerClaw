# Workstream ADR 0061: GlitchTip For Application Exceptions And Task Failures

- ADR: [ADR 0061](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0061-glitchtip-for-application-exceptions-and-task-failures.md)
- Title: Focused exception and failure visibility for internal applications
- Status: ready
- Branch: `codex/adr-0061-glitchtip-failure-signals`
- Worktree: `../proxmox-host_server-glitchtip-failure-signals`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`, `adr-0049-private-api-publication`, `adr-0053-tempo-traces`
- Conflicts With: none
- Shared Surfaces: application errors, workflow failures, issue notifications, release regressions

## Scope

- choose a self-hosted exception-tracking plane
- define first integrations and notification routes
- add a visual issue-focused surface beside logs, traces, and metrics

## Non-Goals

- replacing generalized logging or uptime checks
- collecting sensitive request data without scrubbing rules

## Expected Repo Surfaces

- `docs/adr/0061-glitchtip-for-application-exceptions-and-task-failures.md`
- `docs/workstreams/adr-0061-glitchtip-failure-signals.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private exception-tracking service for internal apps and automation components
- routed failure notifications into approved operator channels

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0061-glitchtip-for-application-exceptions-and-task-failures.md`

## Merge Criteria

- the ADR explains where exception tracking fits relative to logs and traces
- privacy and scrubbing boundaries are explicit

## Notes For The Next Assistant

- start with internal services and workflow-adjacent apps before broader instrumentation
