# Workstream: docker-runtime-lv3 Root Disk Expansion

## Purpose

Expand the live `docker-runtime-lv3` root disk to relieve critical disk
pressure before additional Docker workloads are deployed.

## Scope

- Proxmox VMID `120`
- Virtual disk `scsi0`
- Guest root partition `/dev/sda1`
- Target size: `256G`, matching the current repository-declared desired VM disk
  size and satisfying the requested `200GB+` expansion.

## Plan

1. Verify live VM identity and current disk size from Proxmox.
2. Verify guest block layout and filesystem usage.
3. Resize Proxmox `scsi0` online with `qm resize 120 scsi0 256G`.
4. Grow `/dev/sda1` inside the guest with `growpart /dev/sda 1`.
5. Grow the ext4 filesystem with `resize2fs /dev/sda1`.
6. Record before/after evidence in a live-apply receipt.

## Coordination Notes

The active `ws-pm-tools-deploy` workstream owns service registry and topology
surfaces for project-management-tool deployment. This workstream avoids those
files and records only the operational disk expansion evidence.

Plane sync was skipped from this isolated worktree because the sync script
writes `.local/plane/aw-auth.json` into the active repository root, which would
copy credential state into a worktree. The durable fallback is this workstream
file plus the live-apply receipt.

## Completion Notes

Completed on 2026-07-01.

- Proxmox `qm config 120` before resize:
  `scsi0: local:120/vm-120-disk-0.qcow2,size=128G`
- Proxmox `qm config 120` after resize:
  `scsi0: local:120/vm-120-disk-0.qcow2,size=256G`
- Guest `growpart /dev/sda 1` expanded partition 1 from 268173279 sectors to
  536608735 sectors.
- Guest `resize2fs /dev/sda1` completed online for the mounted root
  filesystem.
- Guest `df -h /` improved from `126G 120G 1.2G 100%` to
  `252G 120G 122G 50%`.
- Runtime health check: Docker service remained `active`, and `sudo docker
  info` reported Docker 29.5.1 with 40 containers running.

Receipt:
`receipts/live-applies/2026-07-01-ws-docker-runtime-disk-expand-live-apply.json`

## PR And CI

Draft PR: `https://github.com/baditaflorin/ServerClaw/pull/32`

GitHub Actions run `28524046655` did not execute the checks. Both
`release-readiness` and `validate` failed at job startup with:

> The job was not started because your account is locked due to a billing issue.

This is an external GitHub account/billing blocker, not a branch validation
failure.
