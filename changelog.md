# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- implement ADR 0411/0412: provision-account/deprovision-account agent tools with live Keycloak auth, Windmill daily account-expiry reaper, nginx @lv3_forbidden 403 error page, and LibreChat accounts tool pack
- align live-apply-service descriptor loading with ADR 0372 playbook composition, add missing keycloak/searxng service wrappers, and verify the include-based playbook tests
- live-apply ADR 0361 to reconcile the Semaphore Keycloak OIDC integration and record verified controller auth evidence

## 0.178.78 (2026-04-10)

- fix: Quote unquoted Jinja2 template in backup_vm_api_token_local_file for shell safety
- fix: Remove duplicate repo_intake entry in platform_services.yml registry
- fix: Escape $PLATFORM_OPERATOR_EMAIL in workflow-catalog.json for Jinja2 compatibility
- fix: Escape Prometheus template syntax in alert rules for Jinja2 rendering compatibility
- verified: Phase 6 cosmetic cleanup stable in production (118/118 convergence tasks passing)

## 0.178.77

- Harbor OIDC fix, public release readiness, ADR 0385-0388 IoC + OIDC centralization, bootstrap and Docker dev, ADR 0373 Phase 4, multi-instance deployment, operator provisioning, operational fixes

## Latest Release

- [0.178.129 release notes](docs/release-notes/0.178.129.md)

## Previous Releases

- [0.178.123 release notes](docs/release-notes/0.178.123.md)
- [0.178.122 release notes](docs/release-notes/0.178.122.md)
- [0.178.121 release notes](docs/release-notes/0.178.121.md)
- [0.178.120 release notes](docs/release-notes/0.178.120.md)
- [0.178.119 release notes](docs/release-notes/0.178.119.md)
- [0.178.118 release notes](docs/release-notes/0.178.118.md)
- [0.178.117 release notes](docs/release-notes/0.178.117.md)
- [0.178.116 release notes](docs/release-notes/0.178.116.md)
- [0.178.115 release notes](docs/release-notes/0.178.115.md)
- [0.178.114 release notes](docs/release-notes/0.178.114.md)
- [0.178.113 release notes](docs/release-notes/0.178.113.md)
- [0.178.112 release notes](docs/release-notes/0.178.112.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (457 releases)](docs/release-notes/index/2026.md)
