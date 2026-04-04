# Release 0.178.5

- Date: 2026-04-04

## Summary
- closes out ADR 0330 public GitHub readiness by making the controller-local secret contract repo-relative, adding fork-first example inventory and provider/publication profiles, and surfacing the public reference tier through discovery-driven onboarding
- implements ADR 0314 by turning the shared runbook execution path into a resumable human task surface with durable progress, deep-link return-to-task entry, and portal reentry summaries

## Platform Impact
- bumps platform version to 0.130.99 after the exact-main resumable-task reentry flow and its supporting runtime, Keycloak, API gateway, and ops portal repairs were verified live

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
