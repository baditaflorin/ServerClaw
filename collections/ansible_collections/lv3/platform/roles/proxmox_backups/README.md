# proxmox_backups

Converges managed Proxmox storage and backup job entries.

Inputs: `proxmox_backup_storage`, `proxmox_backup_jobs`, `proxmox_backup_jobs_marker_id`, and any required controller-local secret material.
Outputs: storage configuration, storage secrets, and scheduled backup jobs in pmxcfs.
