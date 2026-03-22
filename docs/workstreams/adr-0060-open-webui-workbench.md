# Workstream ADR 0060: Open WebUI For Operator And Agent Workbench

- ADR: [ADR 0060](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0060-open-webui-for-operator-and-agent-workbench.md)
- Title: Internal conversational workbench for operators and supervised agents
- Status: ready
- Branch: `codex/adr-0060-open-webui-workbench`
- Worktree: `../proxmox_florin_server-open-webui-workbench`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0048-command-catalog`, `adr-0056-keycloak-sso`
- Conflicts With: none
- Shared Surfaces: workflow catalog, receipts, status docs, governed tools, operator sessions

## Scope

- choose a private conversational workbench for operator and agent use
- constrain data sources and tool exposure to approved surfaces
- support review and supervised execution rather than broad shell access

## Non-Goals

- exposing arbitrary root access through chat
- treating model output as unreviewed authority

## Expected Repo Surfaces

- `docs/adr/0060-open-webui-for-operator-and-agent-workbench.md`
- `docs/workstreams/adr-0060-open-webui-workbench.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private operator and agent workbench backed by approved model connectors
- narrowed tool integrations for platform context and governed actions

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0060-open-webui-for-operator-and-agent-workbench.md`

## Merge Criteria

- the ADR is explicit about data boundaries and tool restrictions
- supervised action rules remain aligned with the command catalog

## Notes For The Next Assistant

- start with read-heavy capabilities before exposing mutating tools
