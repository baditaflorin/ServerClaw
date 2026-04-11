# Workstream ADR 0060: Open WebUI For Operator And Agent Workbench

- ADR: [ADR 0060](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0060-open-webui-for-operator-and-agent-workbench.md)
- Title: Internal conversational workbench for operators and supervised agents
- Status: live_applied
- Branch: `codex/adr-0060-open-webui-workbench`
- Worktree: `../proxmox-host_server-open-webui-workbench`
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
- `docs/runbooks/configure-open-webui.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `playbooks/open-webui.yml`
- `roles/open_webui_runtime/`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/control-plane-lanes.json`
- `config/controller-local-secrets.json`
- `workstreams.yaml`

## Expected Live Surfaces

- a private operator and agent workbench backed by approved model connectors
- narrowed tool integrations for platform context and governed actions

## Verification

- `make syntax-check-open-webui`
- `make converge-open-webui`
- `curl -I http://100.118.189.95:8008/`
- `curl -s -X POST http://100.118.189.95:8008/api/v1/auths/signin -H "Content-Type: application/json" -d "{\"email\":\"ops@example.com\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/open-webui/admin-password.txt)\"}"`
- `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml docker-runtime -m shell -a 'docker compose --env-file /opt/open-webui/open-webui.env --file /opt/open-webui/docker-compose.yml ps' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`

## Merge Criteria

- the ADR is explicit about data boundaries and tool restrictions
- supervised action rules remain aligned with the command catalog

## Notes For The Next Assistant

- start with read-heavy capabilities before exposing mutating tools

## Live Apply Notes

- Live apply completed on `2026-03-22`.
- `docker-runtime` now serves Open WebUI from `/opt/open-webui` and the Proxmox host publishes it privately on `http://100.118.189.95:8008`.
- Repo-managed bootstrap auth is verified for `ops@example.com`, and the admin session shows web search, image generation, code interpreter, and direct tool servers disabled by policy.
