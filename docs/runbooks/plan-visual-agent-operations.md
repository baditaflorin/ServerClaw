# Visual And Agent Operations Roadmap

## Purpose

This runbook groups the next proposed ADR set for a more visual, inspectable, and agent-friendly operations plane.

The target outcome is a platform where humans and agents can:

- see infrastructure, runtime, network, and application state in dedicated visual tools
- collaborate around alerts, approvals, and findings
- use governed interfaces instead of broad shell access by default
- correlate metrics, logs, traces, events, and receipts without reconstructing everything by hand

ADR 0052, ADR 0053, ADR 0059, and ADR 0060 are now implemented and live; the remaining ADRs in this roadmap stay proposed.

## Proposed ADR Map

- [ADR 0052](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md): centralized log aggregation and search in Grafana, implemented on `monitoring-lv3`
- [ADR 0053](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md): traces and service maps for internal apps and workflows, implemented on `monitoring-lv3`
- [ADR 0054](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0054-netbox-for-topology-ipam-and-inventory.md): visual topology, IPAM, and inventory plane
- [ADR 0055](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md): read-mostly runtime console for Docker operations, now live privately on `docker-runtime-lv3`
- [ADR 0056](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0056-keycloak-for-operator-and-agent-sso.md): shared SSO for internal apps
- [ADR 0057](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md): ChatOps and collaboration surface
- [ADR 0058](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0058-nats-jetstream-for-internal-event-bus-and-agent-coordination.md): internal event backbone for workflows and agents
- [ADR 0059](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0059-ntopng-for-private-network-flow-visibility.md): private network flow visibility
- [ADR 0060](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0060-open-webui-for-operator-and-agent-workbench.md): supervised conversational workbench for operators and agents
- [ADR 0061](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0061-glitchtip-for-application-exceptions-and-task-failures.md): exception and task-failure visibility

Current implementation note:

- ADR 0053 is now live on `monitoring-lv3` with Tempo, Prometheus-backed service graphs, and a shared OTLP collector
- ADR 0059 is now live as host-local `ntopng` capture on `proxmox_florin`, with operator-only access on `http://100.118.189.95:3001`

## Recommended Rollout Order

1. extend visibility first
   - logs, traces, and network visibility are now live; topology and operator identity are the next visibility-adjacent priorities before adding more mutation surfaces
   - priority: ADR 0054, ADR 0056
2. make topology browsable
   - add NetBox once the platform already has good canonical metadata to sync
   - priority: ADR 0054
3. standardize operator identity
   - add shared SSO before multiplying internal UIs
   - priority: ADR 0056
4. add bounded runtime control
   - expose runtime inspection and narrow action surfaces only after identity and command rules are clear
   - priority: ADR 0055

## Current Implemented Step

- ADR 0055 is now live as a private Portainer surface on `docker-runtime-lv3` with host-side Tailscale publication at `https://100.118.189.95:9444` and a repo-managed wrapper for read-mostly inspection plus bounded restarts.
5. add human and agent coordination layers
   - introduce chat and event distribution for approvals, notifications, and handoffs
   - priority: ADR 0057, ADR 0058
6. add the conversational workbench
   - ADR 0060 is now live as a private Open WebUI workbench on `docker-runtime-lv3`
   - keep it read-heavy until ADR 0069 and ADR 0070 add governed tools and repo-grounded context
7. tighten application-level failure visibility
   - add exception tracking when internal apps and workflows are ready to emit structured failures
   - priority: ADR 0061

## Placement Guidance

The pragmatic first placement for these services is:

- `monitoring-lv3` for Loki and Tempo if the monitoring VM has enough capacity
- `proxmox_florin` for ntopng, where `vmbr10` and `vmbr0` can be observed directly without adding a mirror or `nProbe`
- `docker-runtime-lv3` for NetBox, Portainer, Keycloak, Mattermost, NATS, Open WebUI, and GlitchTip
- `postgres-lv3` for applications that need a dedicated relational backend

This keeps the first rollout aligned with the current single-node-first topology. If the control-plane blast radius grows too large, a dedicated control-plane VM can be introduced in a later ADR.

Current state:

- ADR 0053 is now live with Tempo, Prometheus-backed service-graph metrics, and a shared OTLP collector on `monitoring-lv3`
- the first instrumented internal path is the private mail gateway on `docker-runtime-lv3`
- ADR 0052 is now live with centralized Loki search for the Proxmox host, `nginx-lv3`, and `docker-runtime-lv3`

## Operating Principles

- keep internal and operator-facing surfaces private-first
- preserve the repository as the design authority
- make UI-based mutation the exception, not the default
- require receipts or equivalent evidence whenever a live change is applied
- give agents named tools and events, not generic root shells

## Verification Targets

Future implementation should be considered successful only when:

- operators can inspect logs, traces, runtime state, and network flow without broad SSH access
- internal apps share one identity model instead of separate local accounts
- agents can present findings and trigger approved workflows through governed surfaces
- the visual tools remain consistent with repo truth instead of drifting into separate undocumented systems
