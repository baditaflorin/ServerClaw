# ADR 0052: Centralized Log Aggregation With Grafana Loki

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

## Boundaries

- Loki is for searchable operational logs, not for immutable evidence records.
- Structured live-apply receipts remain the canonical repo-side proof of change.
- Centralized logging must not become a reason to expose internal services publicly.
