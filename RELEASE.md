# Release 0.167.0

- Date: 2026-03-26

## Summary
- deploy the repo-managed Dozzle hub on `docker-runtime-lv3`, join the `docker-build-lv3` and `monitoring-lv3` agents, and publish `logs.lv3.org` behind the shared Keycloak-authenticated edge
- harden the live apply path so Dozzle convergence also updates the Proxmox guest firewall, verifies the hub through its HTTP healthcheck, and keeps post-verify probes scoped to the owning VM

## Platform Impact
- repository version advances to 0.167.0; platform version advances to 0.130.17 with the first ADR 0150 live-apply receipt recorded for the Dozzle rollout on production.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
