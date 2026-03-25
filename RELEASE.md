# Release 0.147.0

- Date: 2026-03-25

## Summary
- Implemented ADR 0147 with a private Vaultwarden service on `docker-runtime-lv3`, a PostgreSQL backend on `postgres-lv3`, step-ca-issued internal TLS, and a Tailscale-only hostname at `https://vault.lv3.org`.
- Added the Vaultwarden runtime and PostgreSQL roles, service catalogs, alerting and dashboard surfaces, image-scan receipts, the deployment runbook, and the bounded admin bootstrap invite flow for `ops@lv3.org`.

## Platform Impact
- no live platform version bump yet; this release merges ADR 0147 with the repo-managed private Vaultwarden service, catalogs, runbook, and verification surfaces before the first live apply from main

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
