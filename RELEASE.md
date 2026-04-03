# Release 0.177.152

- Date: 2026-04-03

## Summary
- implements ADR 0299 by promoting ntfy to the governed self-hosted push notification channel, wiring the governed topic and credential contracts across Ansible, Gitea, Windmill, SBOM, and k6 publishers, and verifying the public publish path plus the mainline service replay

## Platform Impact
- Implements ADR 0299 by promoting ntfy to the governed self-hosted push notification channel and validating the mainline replay.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
