# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- `group_vars/all`: promote all `openbao_*_local_file` artifact-path variables from `openbao_runtime` role defaults to `group_vars/all/main.yml` — multiple standalone plays reference these directly without including the role (role defaults are never loaded); fixes `'openbao_controller_approle_local_file' is undefined` (and 6 sibling variables) on postgres hosts and any other play that consumers OpenBao credentials without the full role

## Latest Release

- [0.178.170 release notes](docs/release-notes/0.178.170.md)

## Previous Releases

- [0.178.169 release notes](docs/release-notes/0.178.169.md)
- [0.178.168 release notes](docs/release-notes/0.178.168.md)
- [0.178.167 release notes](docs/release-notes/0.178.167.md)
- [0.178.166 release notes](docs/release-notes/0.178.166.md)
- [0.178.165 release notes](docs/release-notes/0.178.165.md)
- [0.178.164 release notes](docs/release-notes/0.178.164.md)
- [0.178.163 release notes](docs/release-notes/0.178.163.md)
- [0.178.162 release notes](docs/release-notes/0.178.162.md)
- [0.178.161 release notes](docs/release-notes/0.178.161.md)
- [0.178.160 release notes](docs/release-notes/0.178.160.md)
- [0.178.159 release notes](docs/release-notes/0.178.159.md)
- [0.178.158 release notes](docs/release-notes/0.178.158.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (495 releases)](docs/release-notes/index/2026.md)
