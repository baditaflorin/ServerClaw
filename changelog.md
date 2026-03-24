# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- Implemented ADR 0122 with a repo-managed Windmill operator access admin app for browser-first operator onboarding, off-boarding, roster reconciliation, and per-operator inventory lookup.
- Seeded the existing operator workflow wrappers and the new raw app bundle through `windmill_runtime`, so the private Windmill workspace can be bootstrapped from repository state.
- Added the ADR 0122 runbook plus focused tests for the raw app bundle, Windmill seed metadata, and the new roster and inventory wrapper scripts.
- Hardened the OpenBao runtime converge to enforce managed ownership of `/opt/openbao/logs/audit.log`, preventing the service from resealing itself after Docker restarts.

## Latest Release

- [0.119.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.119.1.md)
