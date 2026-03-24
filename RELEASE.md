# Release 0.128.0

- Date: 2026-03-24

## Summary
- Implemented ADR 0133 so operator-facing portal services now default to authentication instead of public exposure.
- Added explicit auth classification to every governed hostname in `config/subdomain-catalog.json`, with schema and validator enforcement for justified public exceptions.
- Protected `docs.lv3.org` and `changelog.lv3.org` with the shared Keycloak-backed edge auth flow, while keeping `ops.lv3.org` on the same pattern and preserving Grafana's non-anonymous login boundary.
- Expanded the shared portal auth proxy to issue a `.lv3.org` cookie so one Keycloak session covers the protected browser portals.
- Added focused validation and role tests, plus the ADR 0133 workstream and runbook documentation for the auth-by-default policy.
- Corrected the edge template lookup used for protected hostnames so the intended auth policy actually renders into live NGINX configuration.

## Platform Impact
- repository version advances to 0.128.0; live platform version advances to 0.114.7 after ADR 0133 was applied on nginx-lv3 and unauthenticated access to `ops.lv3.org`, `docs.lv3.org`, and `changelog.lv3.org` was blocked at the edge

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
