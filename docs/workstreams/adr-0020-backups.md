# Workstream ADR 0020: Initial Storage And Backup Model

- ADR: [ADR 0020](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0020-initial-storage-and-backup-model.md)
- Title: Initial storage and backup rollout
- Status: merged
- Branch: `codex/adr-0020-backups`
- Worktree: `../proxmox_florin_server-backups`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `/etc/pve/storage.cfg`, `/etc/pve/jobs.cfg`, backup retention policy, restore validation workflow

## Scope

- define the first steady-state storage model for the single-node Proxmox host
- configure an external off-host backup target through Proxmox-managed storage
- schedule backups for the managed guest VM set
- document what stays local-only versus what is expected to exist off-host
- document verification, restore drills, and rollback notes

## Non-Goals

- Tailscale rollout
- monitoring rollout
- guest disk migration away from the current local runtime storage
- deployment of a separate Proxmox Backup Server

## Expected Repo Surfaces

- `roles/` for storage and backup automation
- `inventory/host_vars/proxmox_florin.yml`
- `docs/runbooks/`
- `docs/adr/0020-initial-storage-and-backup-model.md`
- `README.md`
- `workstreams.yaml`

## Expected Live Surfaces

- external CIFS backup storage entry in Proxmox
- scheduled vzdump job configuration
- off-host backup verification path for VM restores

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesh get /storage/lv3-backup-cifs --output-format json-pretty'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesh get /cluster/backup/backup-lv3-nightly --output-format json-pretty'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pvesm list lv3-backup-cifs --vmid 110'`

## Merge Criteria

- storage and backup automation is idempotent
- retention and restore expectations are documented
- the workstream registry and this document are current
- no speculative `versions/stack.yaml` changes are introduced on the branch

## Notes For The Next Assistant

- keep runtime guest disks on the existing local storage until a separate migration workstream exists
- do not mix backup work with Tailscale or monitoring unless a real dependency appears
- do not bump `VERSION` or `platform_version` on this branch
- this workstream is merged to `main` but not yet applied live
- live apply is blocked until external CIFS target credentials are provided
