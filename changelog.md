# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- completes ADR 0324 exact-main closeout by recording the generated service-catalog assembly receipt on main and refreshing the canonical truth surfaces
- fix Keycloak service topology: upstream now correctly points to runtime-control (10.10.10.92) instead of docker-runtime, preventing nginx edge from reverting sso.lv3.org to the wrong host on next converge

## Latest Release

- [0.178.148 release notes](docs/release-notes/0.178.148.md)

## Previous Releases

- [0.178.147 release notes](docs/release-notes/0.178.147.md)
- [0.178.146 release notes](docs/release-notes/0.178.146.md)
- [0.178.145 release notes](docs/release-notes/0.178.145.md)
- [0.178.144 release notes](docs/release-notes/0.178.144.md)
- [0.178.143 release notes](docs/release-notes/0.178.143.md)
- [0.178.141 release notes](docs/release-notes/0.178.141.md)
- [0.178.140 release notes](docs/release-notes/0.178.140.md)
- [0.178.138 release notes](docs/release-notes/0.178.138.md)
- [0.178.137 release notes](docs/release-notes/0.178.137.md)
- [0.178.136 release notes](docs/release-notes/0.178.136.md)
- [0.178.135 release notes](docs/release-notes/0.178.135.md)
- [0.178.134 release notes](docs/release-notes/0.178.134.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (473 releases)](docs/release-notes/index/2026.md)
