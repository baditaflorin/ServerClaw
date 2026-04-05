# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network

## Latest Release

- [0.178.6 release notes](docs/release-notes/0.178.6.md)

## Previous Releases

- [0.178.5 release notes](docs/release-notes/0.178.5.md)
- [0.178.4 release notes](docs/release-notes/0.178.4.md)
- [0.178.3 release notes](docs/release-notes/0.178.3.md)
- [0.178.2 release notes](docs/release-notes/0.178.2.md)
- [0.178.1 release notes](docs/release-notes/0.178.1.md)
- [0.178.0 release notes](docs/release-notes/0.178.0.md)
- [0.177.153 release notes](docs/release-notes/0.177.153.md)
- [0.177.152 release notes](docs/release-notes/0.177.152.md)
- [0.177.151 release notes](docs/release-notes/0.177.151.md)
- [0.177.150 release notes](docs/release-notes/0.177.150.md)
- [0.177.149 release notes](docs/release-notes/0.177.149.md)
- [0.177.148 release notes](docs/release-notes/0.177.148.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (345 releases)](docs/release-notes/index/2026.md)
