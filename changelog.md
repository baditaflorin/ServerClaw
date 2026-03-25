# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- implemented ADR 0160 with `GoalCompiler.compile_batch()`, controller-local parallel semantic dry-run fan-out, cross-intent conflict classification, staged execution-plan generation, `intent.batch_plan` ledger events, and the new `lv3 intent batch` operator preview
- published ADRs 0153 through 0162 on `main` so the parallel-agent execution backlog is tracked in durable repo documentation

## Latest Release

- [0.143.2 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.143.2.md)
