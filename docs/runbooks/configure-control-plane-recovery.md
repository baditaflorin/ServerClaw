# Configure Control-Plane Recovery

## Purpose

This runbook converges the repository-managed backup, restore-drill, and break-glass support path for the control-plane components on `docker-runtime-lv3`.

## Covered State

The workflow treats the following as first-class control-plane recovery scope:

- `step-ca` runtime files and private password material
- OpenBao configuration plus a managed Raft snapshot
- Windmill database state and runtime bootstrap secrets
- mail-platform runtime files and API credentials
- controller-local recovery references mirrored into the backup store

## Command

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/control-plane-recovery.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Or use the Make target:

```bash
make converge-control-plane-recovery
```

## What The Playbook Does

1. Configures `backup-lv3` as the control-plane recovery store.
2. Installs a dedicated non-human SSH landing user for runtime archive delivery.
3. Configures `docker-runtime-lv3` to export scheduled control-plane backups.
4. Creates a scoped OpenBao backup token used only for managed Raft snapshots.
5. Builds a controller-local recovery bundle and mirrors it into `backup-lv3`.
6. Enables a scheduled restore drill on `backup-lv3`.
7. Runs one immediate backup and one immediate restore drill for verification.

## Scheduled Policy

- runtime backup timer: `*-*-* 01,07,13,19:15:00`
- restore drill timer: `*-*-* 05:45:00`

The current cadence is intentionally faster than typical VM-only backup policy because short-lived secrets and internal certificates change more often than guest disks.

## Verification

Check the backup timer on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'sudo systemctl status lv3-control-plane-backup.timer --no-pager'
```

Check the restore-drill timer on `backup-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.60 'sudo systemctl status lv3-control-plane-restore-drill.timer --no-pager'
```

Inspect the latest runtime backup landing zone:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.60 'ls -lah /srv/control-plane-recovery/runtime/docker-runtime-lv3/latest'
```

Inspect the restore-drill result:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.60 'sudo cat /srv/control-plane-recovery/drills/last-restore-drill.json'
```

Inspect the controller recovery bundle:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.60 'ls -lah /srv/control-plane-recovery/controller'
```

## Break-Glass Notes

- The controller bundle includes repo-managed recovery references needed to reconnect to the live control plane.
- The root break-glass SSH private key remains an external dependency and is intentionally not copied into the archived bundle.
- Treat `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519` as a separately preserved recovery secret.

## Restore Orientation

Use the archived component files in `backup-lv3` as the source of truth for service-specific recovery:

- `step-ca.tar.zst` for CA runtime files and passwords
- `openbao-config.tar.zst` plus `openbao-raft.snap` for OpenBao
- `windmill-db.dump` plus `windmill-files.tar.zst` for Windmill
- `mail-platform.tar.zst` for Stalwart and gateway state
- `controller-recovery-bundle.tar.zst` plus `control-plane-recovery-manifest.json` for controller-local references

The automated restore drill validates archive integrity and key file presence, but it does not yet recreate the full services on an isolated host.

## Limitation

This workflow improves control-plane recovery materially, but it still shares the same physical host failure domain as the rest of the platform. It is not a substitute for off-host replication or a second recovery site.
