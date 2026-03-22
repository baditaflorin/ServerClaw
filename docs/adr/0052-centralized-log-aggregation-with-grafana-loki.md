# ADR 0052: Centralized Log Aggregation With Grafana Loki

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.50.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

Metrics and uptime views already exist, but the platform still lacks one visual place to inspect:

- Proxmox host logs
- guest system logs
- Docker container logs
- workflow and automation execution logs
- correlation between alerts, metrics, and log lines

Without centralized logs, humans and agents fall back to SSH plus grep on individual nodes. That does not scale as more services, workflows, and operators are added.

## Decision

We will add a centralized log plane using Grafana Loki.

Initial design:

1. Loki runs as part of the monitoring stack and is visible through the existing Grafana surface.
2. Host, guest, and container logs are shipped with approved collectors such as Grafana Alloy, Promtail, or another repo-managed collector.
3. Log streams are labeled consistently by host, VM role, service, environment, and control-plane lane where applicable.
4. Retention is tiered so high-volume logs do not crowd out high-value control-plane evidence.

Priority ingestion targets:

- Proxmox host system logs
- NGINX guest logs
- Docker runtime container logs
- Windmill and future control-plane application logs
- backup, certificate, and secret-management service logs once those systems exist

## Consequences

- Operators gain a visual path to investigate failures without logging into each node first.
- Agents can correlate metrics, events, and logs from one query surface.
- Log-label discipline becomes part of the platform contract rather than an afterthought.
- Storage growth and retention policy need explicit management.

## Implementation Notes

- `monitoring-lv3` now runs Loki locally and Grafana provisions a managed `Loki Logs` datasource at `http://127.0.0.1:3100`.
- The monitoring workflow now converges Grafana Alloy on the Proxmox host and all managed guests, keeping the rollout inside the existing `make converge-monitoring` path instead of creating a parallel ad hoc log workflow.
- Guest and host log streams now carry consistent labels for `host`, `node_role`, `environment`, `lane`, and `source`, with additional `service`, `service_name`, `container`, `compose_project`, `log_type`, `unit`, and `syslog_identifier` labels where the source makes them available.
- The initial live rollout verifies three priority ingestion paths: Proxmox host journald logs, `nginx-lv3` file-based NGINX access logs, and `docker-runtime-lv3` Docker container logs for the current control-plane applications.
- Retention is tiered in Loki so general logs default to seven days, NGINX access logs retain for three days, and control-plane container logs retain for 28 days.
- Operator procedures are documented in [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md), and the visual-operations roadmap now treats ADR 0052 as complete instead of proposed-only.

## Boundaries

- Loki is for searchable operational logs, not for immutable evidence records.
- Structured live-apply receipts remain the canonical repo-side proof of change.
- Centralized logging must not become a reason to expose internal services publicly.
