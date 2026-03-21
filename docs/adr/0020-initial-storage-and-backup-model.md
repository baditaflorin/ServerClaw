# ADR 0020: Initial Storage And Backup Model

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform now has a functioning single-node Proxmox host, working guest provisioning, API automation, and a hardened access model. What it still lacks is a clear storage and backup contract.

ADR 0005 already established the top-level direction:

- single-node first
- local runtime storage
- external backups before expansion

This ADR makes that practical for the current platform state. The current guests already run from the existing local Proxmox storage path, and there is no separate Proxmox Backup Server, no cluster storage fabric, and no second node available for replication.

The initial storage and backup model therefore needs to:

- preserve the currently working local runtime layout
- add a simple off-host backup target that Proxmox can manage directly
- define retention and restore expectations up front
- avoid turning backup design into a hidden assumption scattered across runbooks and chat history

## Decision

We will use this initial model:

1. Runtime stays local on the Proxmox host.
   - Managed guest disks remain on the current local Proxmox runtime storage.
   - Template cache, snippets, ISO/template artifacts, and other transient host-local assets remain local-only.
2. Off-host backups use a Proxmox-managed external CIFS storage target.
   - The first external backup target is a CIFS share configured in Proxmox storage, not a second Proxmox node and not Ceph.
   - A separate Proxmox Backup Server remains a possible future improvement, but it is outside this workstream.
3. Managed guest VMs are backed up nightly with Proxmox snapshot backups.
   - Initial backup scope is the current managed VM set: `110`, `120`, `130`, and `140`.
   - The template VM `9000` is excluded because it is reproducible from the pinned Debian cloud image and automation.
   - Backups use `snapshot` mode and `zstd` compression.
4. Retention is enforced in the backup job.
   - Keep last `3`
   - Keep daily `7`
   - Keep weekly `5`
   - Keep monthly `12`
5. The host itself is treated as rebuildable infrastructure, not as an image-backup target in phase one.
   - Host recovery depends on the repository, the documented bootstrap/runbook path, and controller-local secrets that are already stored outside git.
   - This ADR does not introduce bare-metal image backup for the Proxmox host.
6. Restore verification is mandatory.
   - Operators must be able to list backups, inspect backed-up config, and restore a managed VM to a spare VMID without relying on undocumented UI clicks.

## Local-Only Versus External Backup Scope

Local-only and rebuildable in this phase:

- Proxmox host OS installation
- Proxmox packages and node-level package cache
- guest runtime disks on the primary local storage
- Debian cloud image cache
- Proxmox snippets and template artifacts
- template VM `9000`
- controller-local SSH keys, TOTP material, and API token secrets stored under `.local/`

Expected to exist off-host after backup rollout:

- scheduled vzdump archives for VMs `110`, `120`, `130`, and `140`
- backed-up guest configuration embedded in those archives
- backup history consistent with the declared retention rules

## Consequences

- The initial model stays aligned with the existing single-node architecture and avoids an unnecessary storage migration before backups exist.
- Backup automation can be converged with one external dependency: a reachable CIFS share with credentials supplied at execution time.
- Host disaster recovery still depends on the repo and operator-run rebuild procedures, so repo correctness remains critical.
- The monitoring VM becomes explicitly part of the protected guest set, which matches ADR 0011.
- A later move to Proxmox Backup Server, a different off-host storage backend, or guest disk migration will require a follow-up ADR or ADR amendment because those are architecture changes, not just runbook tweaks.

## Sources

- <https://pve.proxmox.com/wiki/Storage:_CIFS>
- <https://pve.proxmox.com/pve-docs-9-beta/chapter-vzdump.html>
- <https://pve.proxmox.com/pve-docs-9-beta/qmrestore.1.html>
- <https://pve.proxmox.com/pve-docs-9-beta/pvescheduler.8.html>
