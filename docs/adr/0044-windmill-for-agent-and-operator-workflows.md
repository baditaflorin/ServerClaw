# ADR 0044: Windmill For Agent And Operator Workflows

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository already has controller-side scripts, workflow catalogs, and validation helpers, but it does not yet have a durable on-platform workflow runtime for:

- scheduled automation
- webhook-triggered automation
- API-triggered task execution
- agent-friendly execution endpoints that can be governed separately from direct shell access

Without that layer, the platform remains split between local controller scripts and ad hoc remote commands.

## Decision

We will use Windmill as the first on-platform workflow runtime for agents and operators.

Initial responsibilities:

1. run repo-managed scripts and flows on demand, by schedule, or by API trigger
2. accept internal HTTP routes and webhooks for automation entry points
3. provide a narrow execution plane for routine tasks that do not justify direct SSH
4. keep bootstrap secrets in repo-managed host-local files until OpenBao is available, and reserve secret-bearing job flows for ADR 0043
5. keep execution metadata, run history, and arguments visible to operators

Initial placement:

- host: `docker-runtime-lv3`
- database: `postgres-lv3`
- exposure: private-only at first, with operator access over private networks and a Tailscale TCP proxy on the Proxmox host

## Consequences

- Agentic operations gain a durable API and workflow surface that is not just "SSH and run commands."
- Routine automations can move from workstation-local execution to a stable server-side control plane.
- The repository remains the source of truth for the scripts and flows; Windmill is the runtime, not the design authority.
- Windmill itself becomes critical operational state and must be backed up and restored deliberately.
- The first live rollout can proceed before ADR 0043 only because the seeded repo-managed jobs do not depend on third-party long-lived secrets.

## Boundaries

- Windmill must not become a place where operators hand-edit business logic that never returns to git.
- Direct root credentials must not be stored inside Windmill.
- Long-lived secrets used by Windmill jobs must be fetched from OpenBao or other approved authorities, not hard-coded in flow definitions.

## Sources

- [What is Windmill?](https://www.windmill.dev/docs/intro)
- [Self-host Windmill](https://www.windmill.dev/docs/advanced/self_host)
- [Triggers](https://www.windmill.dev/docs/getting_started/triggers)
- [HTTP routes](https://www.windmill.dev/docs/core_concepts/http_routing)

## Implementation Notes

- The repo now defines a dedicated Windmill automation surface through [playbooks/windmill.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/windmill.yml), [roles/windmill_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/windmill_postgres), [roles/windmill_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/windmill_runtime), and the seeded script under [config/windmill](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill).
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json) now exposes `converge-windmill` as the canonical entry point with explicit preflight, validation, and verification metadata.
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json) now records the controller-local Windmill bootstrap artifacts consumed by the workflow.
- Operator usage is documented in [docs/runbooks/configure-windmill.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-windmill.md).
- Live application is intentionally still pending, so the platform implementation metadata remains `not yet`.
