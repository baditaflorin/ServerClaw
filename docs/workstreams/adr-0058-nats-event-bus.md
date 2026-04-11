# Workstream ADR 0058: NATS JetStream For Internal Event Bus And Agent Coordination

- ADR: [ADR 0058](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0058-nats-jetstream-for-internal-event-bus-and-agent-coordination.md)
- Title: Internal event backbone for workflows, alerts, and agents
- Status: ready
- Branch: `codex/adr-0058-nats-event-bus`
- Worktree: `../proxmox-host_server-nats-event-bus`
- Owner: codex
- Depends On: `adr-0045-communication-lanes`, `adr-0046-identity-classes`, `adr-0047-short-lived-creds`
- Conflicts With: none
- Shared Surfaces: workflow events, alert events, agent handoffs, internal consumers

## Scope

- choose NATS JetStream as the internal event bus
- define first event subjects and consumer boundaries
- support durable fan-out for agentic and control-plane flows

## Non-Goals

- replacing primary data stores with an event bus
- publishing internal event traffic to public endpoints

## Expected Repo Surfaces

- `docs/adr/0058-nats-jetstream-for-internal-event-bus-and-agent-coordination.md`
- `docs/workstreams/adr-0058-nats-event-bus.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private event backbone for internal control-plane events
- named subjects and durable consumers for selected workflows

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0058-nats-jetstream-for-internal-event-bus-and-agent-coordination.md`

## Merge Criteria

- the ADR defines event categories, scoping, and retention expectations
- event-bus boundaries versus databases and receipts are explicit

## Notes For The Next Assistant

- start with a small set of operational events instead of trying to event-source the whole platform
