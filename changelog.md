# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- tighten the Windmill PostgreSQL automation so `windmill_admin` converges with `CREATEROLE`, which restores Windmill-managed secondary role creation on current `1.662.0` runtimes
- converge Windmill schedule `enabled` flags from the repo-declared state, fixing pre-existing ADR 0154 schedule rows that stayed disabled after earlier seeds
- record the first verified ADR 0154 live apply in platform version `0.130.5` with the corresponding Windmill receipt and workstream status updates

## Latest Release

- [0.157.2 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.157.2.md)
