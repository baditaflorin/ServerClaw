# Release 0.177.94

- Date: 2026-03-30

## Summary
- implemented ADR 0270 by adding a shared Docker publication assurance helper, catalog-declared host publication contracts, post-verify repair hooks, read-only observation checks, and live-apply recovery hardening for Harbor, Keycloak, OpenBao, Outline, and Langfuse when Docker publication drift surfaced during replay

## Platform Impact
- keeps platform version at 0.130.62 while integrating the already live-applied ADR 0270 Docker publication self-healing and recovery hardening on top of the 0.177.93 mainline.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
