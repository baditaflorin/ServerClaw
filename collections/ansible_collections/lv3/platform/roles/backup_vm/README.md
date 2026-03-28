# backup_vm

Configures the dedicated backup guest as a Proxmox Backup Server node.

Inputs: `backup_vm_ipv4`, datastore settings, PBS API identity settings, Proxmox repository settings, and seed snapshot store settings.
Outputs: a mounted PBS datastore, a local PBS API token file on the controller, a managed seed snapshot store under `/var/lib/lv3/seed-data-snapshots`, and a running PBS service on `backup-lv3`.
