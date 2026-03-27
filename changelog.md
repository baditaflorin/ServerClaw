# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- implemented ADR 0177 run namespace partitioning so controller-local mutable tooling now resolves a canonical `.local/runs/<run_id>/` bundle with dedicated `ansible/`, `tofu/`, `rendered/`, `logs/`, and `receipts/` subpaths
- routed Makefile live-apply and OpenTofu entrypoints through the new namespace wrapper, updated `scripts/tofu_exec.sh` to keep isolated runtime copies and plan outputs, and forwarded `LV3_RUN_ID` through the remote execution gateway for build-server OpenTofu runs
- added focused coverage for namespaced drift and diff execution, including parallel OpenTofu adapter assertions that concurrent runs use distinct per-run plan directories
## Latest Release

- [0.177.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.177.1.md)

## Previous Releases

- [0.177.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.177.0.md)

- [0.176.7 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.7.md)
- [0.176.6 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.6.md)
- [0.176.5 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.5.md)
- [0.176.4 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.4.md)
- [0.176.3 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.3.md)
- [0.176.2 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.2.md)
- [0.176.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.1.md)
- [0.176.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.176.0.md)
- [0.175.2 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.175.2.md)
- [0.175.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.175.1.md)
- [0.175.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.175.0.md)
- [0.174.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.174.1.md)
- [0.174.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.174.0.md)
- [0.172.1 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.172.1.md)
- [0.172.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.172.0.md)
- [0.171.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.171.0.md)
- [0.170.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.170.0.md)
