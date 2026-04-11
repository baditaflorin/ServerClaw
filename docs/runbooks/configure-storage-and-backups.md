# Configure Storage And Backups

## Purpose

This runbook captures the first operator path for converging the storage and backup model defined by ADR 0020.

## Model Summary

- guest runtime storage stays local on the Proxmox host
- off-host backups go to a Proxmox-managed external CIFS storage
- the managed backup set is VMs `110`, `120`, `130`, and `140`
- the template VM `9000` is intentionally excluded
- the Proxmox host itself is rebuildable-from-repo in this phase, not image-backed-up

## Required Environment

Export the external CIFS target details before running the playbook:

```bash
export PROXMOX_BACKUP_CIFS_SERVER=...
export PROXMOX_BACKUP_CIFS_SHARE=...
export PROXMOX_BACKUP_CIFS_USERNAME=...
export PROXMOX_BACKUP_CIFS_PASSWORD=...
```

## Command

```bash
make configure-backups
```

## What The Playbook Does

1. Installs the CIFS client package needed by the Proxmox host.
2. Writes the Proxmox-managed secret file for the external CIFS storage.
3. Converges the external backup storage entry `lv3-backup-cifs`.
4. Converges the nightly backup job `backup-nightly`.
5. Verifies that Proxmox can read the storage entry and the backup job config.

## Backup Policy

- Mode: `snapshot`
- Compression: `zstd`
- Schedule: daily at `02:30`
- Notification path: Proxmox notification system
- Retention:
  - keep last `3`
  - keep daily `7`
  - keep weekly `5`
  - keep monthly `12`

## Verification

Inspect the converged storage entry:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesh get /storage/lv3-backup-cifs --output-format json-pretty'
```

Inspect the scheduled backup job:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesh get /cluster/backup/backup-nightly --output-format json-pretty'
```

List the backup files for one managed VM after the first successful run:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesm list lv3-backup-cifs --vmid 110'
```

Run one ad hoc backup to validate the target before waiting for the nightly schedule:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo vzdump 110 --storage lv3-backup-cifs --mode snapshot --compress zstd --notification-mode notification-system'
```

## Restore-Oriented Checks

Inspect the configuration embedded in the latest backup archive for VM `110`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'latest=$(sudo pvesm list lv3-backup-cifs --vmid 110 | awk '\''NR==2 {print $1}'\''); sudo pvesm extractconfig "$latest" qemu-server.conf'
```

Manual restore drill to a spare VMID without starting the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'latest=$(sudo pvesm list lv3-backup-cifs --vmid 110 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 9101 --storage local --unique 1'
```

Post-restore checks:

- `sudo qm config 9101`
- `sudo qm status 9101`
- if you need a boot test, disconnect or reconfigure networking before the first start to avoid duplicate IP or MAC conflicts

Cleanup after a restore drill:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo qm stop 9101 || true; sudo qm destroy 9101 --destroy-unreferenced-disks 1 --purge 1'
```

## Rollback Notes

If the new backup target or schedule needs to be removed after a live apply:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pvesh delete /cluster/backup/backup-nightly && sudo pvesh delete /storage/lv3-backup-cifs'
```

Then remove the corresponding automation config from the repo or adjust it before the next run, otherwise the playbook will recreate the resources.
