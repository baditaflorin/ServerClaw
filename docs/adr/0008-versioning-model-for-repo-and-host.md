# ADR 0008: Versioning Model For Repo And Host

- Status: Accepted
- Date: 2026-03-21

## Context

This project needs to answer two different questions clearly:

1. What version is the repository contract and automation at?
2. What version is the real server and platform state at?

Without separating those concerns, agent and human operators will blur:

- desired state vs actual state
- docs changes vs infrastructure changes
- breaking changes vs additive changes

## Decision

We will use two semantic version streams plus one observed-state registry.

1. Repository version
   - stored in the root `VERSION` file
   - represents the version of this repository's automation, runbooks, ADR set, and operational contract
2. Platform version
   - stored in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml`
   - represents the intended release version of the managed Proxmox platform for this server
3. Observed state
   - also stored in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml`
   - records the latest known real-world state of the server, including OS and Proxmox version

## Version bump rules

Repository version (`VERSION`):

- bump `MAJOR` for breaking changes to automation contracts, repository structure, inventory conventions, or operating procedures
- bump `MINOR` for backward-compatible capabilities such as new roles, new playbooks, or new documented workflows
- bump `PATCH` for corrections that do not materially change how the platform is operated

Platform version (`versions/stack.yaml`):

- bump `MAJOR` for disruptive platform shifts such as a new Proxmox major, storage model rewrite, or network architecture change
- bump `MINOR` for additive infrastructure capabilities such as backups, monitoring, additional managed networks, or hardened access controls
- bump `PATCH` for safe incremental platform adjustments and state reconciliations

Observed state:

- update whenever the real server state changes or is newly verified
- do not use observed values as a substitute for version bumps

## Consequences

- Agents and humans can discuss repository maturity separately from platform maturity.
- Commits that change infrastructure intent should update the version files explicitly.
- The version registry becomes the first place to check before making changes or troubleshooting drift.
