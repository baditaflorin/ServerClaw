# Release 0.148.0

- Date: 2026-03-25

## Summary
- Implemented ADR 0151 with repo-managed `n8n` on `docker-runtime-lv3`, PostgreSQL persistence on `postgres-lv3`, edge publication at `https://n8n.lv3.org`, and public webhook path handling under the shared ingress model.
- Added the `n8n_postgres` and `n8n_runtime` roles, service and secret catalog wiring, edge auth path exceptions, the operator runbook, and the pinned image-scan receipts for the new automation surface.

## Platform Impact
- no live platform version bump yet; this release merges ADR 0151 with the repo-managed n8n runtime, PostgreSQL-backed persistence, shared-edge publication, and the bounded webhook exposure model before the first mainline live apply

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
