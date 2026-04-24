# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- `platform_facts.py` filters: add optional `default` parameter to `platform_service_url`, `platform_service_port`, `platform_service_host` — when a service or key is absent and a default is provided, return the default instead of raising `AnsibleFilterError`; fixes fatal task-arg-resolution crash on forks that omit optional services (e.g. ntfy)
- `group_vars/all/main.yml`: pass `''` default to `platform_service_url('ntfy', 'internal')` so the ntfy start notification is gracefully skipped on deployments that do not run ntfy

## Latest Release

- [0.178.166 release notes](docs/release-notes/0.178.166.md)

## Previous Releases

- [0.178.165 release notes](docs/release-notes/0.178.165.md)
- [0.178.164 release notes](docs/release-notes/0.178.164.md)
- [0.178.163 release notes](docs/release-notes/0.178.163.md)
- [0.178.162 release notes](docs/release-notes/0.178.162.md)
- [0.178.161 release notes](docs/release-notes/0.178.161.md)
- [0.178.160 release notes](docs/release-notes/0.178.160.md)
- [0.178.159 release notes](docs/release-notes/0.178.159.md)
- [0.178.158 release notes](docs/release-notes/0.178.158.md)
- [0.178.157 release notes](docs/release-notes/0.178.157.md)
- [0.178.156 release notes](docs/release-notes/0.178.156.md)
- [0.178.155 release notes](docs/release-notes/0.178.155.md)
- [0.178.154 release notes](docs/release-notes/0.178.154.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (491 releases)](docs/release-notes/index/2026.md)
