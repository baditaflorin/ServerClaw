# Release 0.178.129

- Date: 2026-04-13

## Summary
- implement ADR 0411/0412: provision-account/deprovision-account agent tools with live Keycloak auth, Windmill daily account-expiry reaper, nginx @lv3_forbidden 403 error page, and LibreChat accounts tool pack
- align live-apply-service descriptor loading with ADR 0372 playbook composition, add missing keycloak/searxng service wrappers, and verify the include-based playbook tests
- fix: Quote unquoted Jinja2 template in backup_vm_api_token_local_file for shell safety
- fix: Remove duplicate repo_intake entry in platform_services.yml registry
- fix: Escape $PLATFORM_OPERATOR_EMAIL in workflow-catalog.json for Jinja2 compatibility
- fix: Escape Prometheus template syntax in alert rules for Jinja2 rendering compatibility
- verified: Phase 6 cosmetic cleanup stable in production (118/118 convergence tasks passing)
- Harbor OIDC fix, public release readiness, ADR 0385-0388 IoC + OIDC centralization, bootstrap and Docker dev, ADR 0373 Phase 4, multi-instance deployment, operator provisioning, operational fixes

## Platform Impact
- no live platform version bump; this release updates repository automation, release metadata, and operator tooling only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
