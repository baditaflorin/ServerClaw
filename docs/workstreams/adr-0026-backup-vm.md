# Workstream ADR 0026: Dedicated Backup VM With Local PBS

- ADR: [ADR 0026](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0026-dedicated-backup-vm-with-local-pbs.md)
- Title: Dedicated backup VM rollout
- Status: ready_for_merge
- Branch: `codex/adr-0026-backup-vm`
- Worktree: `../proxmox_florin_server-backup-vm`
- Owner: codex
- Depends On: `adr-0020-backups`
- Conflicts With: none
- Shared Surfaces: `backup-lv3`, `/etc/pve/storage.cfg`, `/etc/pve/jobs.cfg`, guest provisioning, restore validation workflow

## Scope

- create a dedicated backup VM on the internal Proxmox network
- install and configure Proxmox Backup Server inside that VM
- attach the Proxmox host to the new PBS target
- keep backup schedules and restore checks under automation
- document the same-host failure-domain limitation explicitly

## Non-Goals

- off-host replication or second-site backup copy
- Tailscale or public publication for the backup VM
- changing the existing monitoring or Docker workstreams

## Expected Repo Surfaces

- `inventory/`
- `roles/proxmox_guests`
- `roles/proxmox_backups`
- `roles/backup_vm`
- `playbooks/backup-vm.yml`
- `docs/runbooks/`
- `docs/adr/0026-dedicated-backup-vm-with-local-pbs.md`
- `README.md`

## Expected Live Surfaces

- VM `160` on `10.10.10.60`
- PBS datastore and API token on the backup VM
- PBS storage target and backup job config on the Proxmox host

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/backup-vm.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm list | grep 160'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /storage/lv3-backup-pbs --output-format json-pretty'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /cluster/backup/backup-lv3-nightly --output-format json-pretty'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesm list lv3-backup-pbs --vmid 110'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo vzdump 110 --storage lv3-backup-pbs --mode snapshot --compress zstd --notification-mode notification-system'`

## Merge Criteria

- backup VM provisioning is automated and idempotent
- PBS token and datastore creation are automated
- same-host backup limitations and restore workflow are documented
- no speculative `versions/stack.yaml` changes are introduced on the branch

## Notes For The Next Assistant

- this workstream intentionally improves restore operations without claiming off-host disaster recovery
- a later follow-up should add replication or a second-site copy
- do not bump `VERSION` or `platform_version` on this branch
- live validation on 2026-03-22 succeeded for VM `160`, storage `lv3-backup-pbs`, job `backup-lv3-nightly`, and an ad hoc backup artifact for VM `110`
