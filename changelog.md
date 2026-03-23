# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/build/changelog-portal/index.html)
- planned published hostname: [changelog.lv3.org](https://changelog.lv3.org)
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md).

## Unreleased

- packaged the repo-managed Ansible automation as the `lv3.platform` collection under `collections/ansible_collections/lv3/platform/`, migrated role and plugin source-of-truth into that collection, and left compatibility symlinks at the repo root
- rewrote the repo playbooks and role-to-role imports to use `lv3.platform.*` FQCNs, added collection build/install/publish targets, and added the Windmill `collection-publish` helper script
- added shared collection roles for `preflight`, `common_handlers`, `secret_fact`, and `wait_for_healthy`, documented the workflow in a dedicated runbook, and updated ADR 0086 plus workstream metadata to record implementation on `0.85.0`

## Latest Release

- [0.85.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.85.0.md)
