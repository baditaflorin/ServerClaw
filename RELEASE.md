# Release 0.177.122

- Date: 2026-03-31

## Summary
- implements ADR 0303 by enabling PostgreSQL pgaudit query and privilege audit logging, shipping structured audit and connection signals into Loki and Prometheus, and routing unknown-role alerts to ntfy plus NATS with recorded exact-main live-apply evidence

## Platform Impact
- Mainline integration of ADR 0303 on top of repository version 0.177.121 and platform baseline 0.130.78. This release carries the PostgreSQL pgaudit query and privilege audit logging rollout, the repaired unknown-role alert relay and JetStream publication path, and the live-apply automation fixes for non-catalog service gating, restic trigger invocation, and delegated PostgreSQL seed execution.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
