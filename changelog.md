# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- `proxmox_backups/defaults/main.yml`: backup storage ID changed from `config_prefix` to `pve_prefix` — Proxmox storage IDs cannot start with a digit; `0fork` config_prefix → `fork` pve_prefix produces valid ID `fork-backup-pbs`

## Latest Release

- [0.178.167 release notes](docs/release-notes/0.178.167.md)

## Previous Releases

- [0.178.166 release notes](docs/release-notes/0.178.166.md)
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

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (492 releases)](docs/release-notes/index/2026.md)
