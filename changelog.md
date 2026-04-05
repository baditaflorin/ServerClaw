# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- label_studio_runtime: add CSRF_TRUSTED_ORIGINS to env templates (fixes 403 on login behind oauth2_proxy)
- langfuse_runtime: set langfuse_disable_signup=false for automatic Keycloak SSO user provisioning; add extra_hosts hairpin NAT fix for sso.lv3.org in both langfuse-web and langfuse-worker
- adds scripts/langfuse_to_label_studio.py — stdlib sync pipeline from Langfuse traces to Label Studio annotation tasks with deduplication
- adds config/windmill/scripts/langfuse-label-studio-sync.py — Windmill scheduled job wrapper for the sync pipeline
- adds config/serverclaw/skills/shared/human-review-queue/SKILL.md — agent skill for self-queuing decisions for human review

## Latest Release

- [0.178.9 release notes](docs/release-notes/0.178.9.md)

## Previous Releases

- [0.178.8 release notes](docs/release-notes/0.178.8.md)
- [0.178.7 release notes](docs/release-notes/0.178.7.md)
- [0.178.6 release notes](docs/release-notes/0.178.6.md)
- [0.178.5 release notes](docs/release-notes/0.178.5.md)
- [0.178.4 release notes](docs/release-notes/0.178.4.md)
- [0.178.3 release notes](docs/release-notes/0.178.3.md)
- [0.178.2 release notes](docs/release-notes/0.178.2.md)
- [0.178.1 release notes](docs/release-notes/0.178.1.md)
- [0.178.0 release notes](docs/release-notes/0.178.0.md)
- [0.177.153 release notes](docs/release-notes/0.177.153.md)
- [0.177.152 release notes](docs/release-notes/0.177.152.md)
- [0.177.151 release notes](docs/release-notes/0.177.151.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (348 releases)](docs/release-notes/index/2026.md)
