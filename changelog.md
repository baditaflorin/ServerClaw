# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- corrected the ADR 0093 live rollout contract so `ops_portal` uses host port `8092` instead of colliding with the existing GlitchTip host-network listener on `docker-runtime-lv3`
- added the missing `playbooks/services/ops_portal.yml` service entrypoint and made `scripts/mutation_audit.py` self-contained so `make live-apply-service service=ops_portal env=production` works from a clean controller environment

## Latest Release

- [0.114.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.114.0.md)
