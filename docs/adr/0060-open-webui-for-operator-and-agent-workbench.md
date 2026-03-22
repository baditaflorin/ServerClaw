# ADR 0060: Open WebUI For Operator And Agent Workbench

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.50.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform is accumulating structured state, workflows, receipts, dashboards, and future internal APIs, but there is no single workbench where a human can:

- ask for platform context
- inspect approved knowledge sources
- hand work to an agent
- review agent output
- invoke governed tools without falling back to raw shell

## Decision

We will add an internal operator-and-agent workbench using Open WebUI or an equivalent repo-managed LLM console.

Initial expectations:

1. the workbench is private-only
2. model access is mediated through approved connectors, not arbitrary outbound calls
3. exposed tools are limited to governed surfaces such as workflow catalog queries, receipt lookups, status docs, and approved execution endpoints
4. user and bot identities follow the shared SSO and approval model where available

Initial use cases:

- answer operational questions from repo and platform metadata
- draft or review routine changes before execution
- summarize alerts, logs, traces, and receipts for humans
- coordinate with workflow runners instead of invoking broad shell access directly

## Consequences

- Humans gain a central conversational workbench tied to the platform’s approved data and tool surfaces.
- Agents become easier to supervise because tool access can be narrowed to named operations.
- Model governance, prompt hygiene, and data-boundary rules become platform concerns.
- The workbench itself becomes a sensitive operator surface and must be isolated accordingly.

## Boundaries

- The workbench must not expose unrestricted root shell or arbitrary network egress.
- It is an orchestration and review surface, not the source of truth for infrastructure design.
- Any mutating action still follows the command-catalog, approval, and evidence rules.

## Sources

- [Open WebUI environment configuration](https://docs.openwebui.com/reference/env-configuration/)
- [Open WebUI SSO and OAuth troubleshooting](https://docs.openwebui.com/troubleshooting/sso/)
- [Open WebUI MCP extensibility](https://docs.openwebui.com/features/extensibility/mcp/)
- [Open WebUI releases](https://github.com/open-webui/open-webui/releases)

## Implementation Notes

- The repo now deploys Open WebUI through [playbooks/open-webui.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/open-webui.yml) and [roles/open_webui_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/open_webui_runtime) on `docker-runtime-lv3`.
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json), [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json), and [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json) now treat Open WebUI as a named private operator surface with an explicit converge workflow and approval contract.
- Controller-local bootstrap artifacts live under `.local/open-webui/`, while approved model connector settings remain optional and local-only through `provider.env`.
- The live platform now serves Open WebUI privately at `http://100.118.189.95:8008` through the Proxmox host Tailscale proxy, with repo-managed local admin bootstrap verified and direct tool servers, web search, image generation, and code interpreter disabled by policy.
