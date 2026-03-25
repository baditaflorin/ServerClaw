# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- implemented ADR 0129 runbook automation with structured YAML, JSON, and Markdown-front-matter runbook loading, persisted run records, resumable escalations, and mutation-audit execution trace output
- added the `lv3 runbook` CLI path, the Windmill `runbook-executor` wrapper, a repo-managed `runbook-executor` workflow contract, and focused executor coverage for YAML and JSON runbook definitions

## Latest Release

- [0.131.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.131.0.md)
