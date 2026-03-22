# Workstream ADR 0025: Dedicated PostgreSQL VM Baseline

- ADR: [ADR 0025](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0025-dedicated-postgresql-vm-baseline.md)
- Title: Dedicated PostgreSQL VM baseline
- Status: in_progress
- Branch: `codex/adr-0025-postgres-vm`
- Worktree: `../proxmox_florin_server-postgres-vm`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `postgres-lv3`, `playbooks/postgres-vm.yml`, `roles/postgres_vm`, `inventory/group_vars/postgres_guests.yml`

## Scope

- add a dedicated PostgreSQL guest to the Proxmox inventory
- converge a secure PostgreSQL baseline on that guest
- enforce a guest-local firewall and explicit `pg_hba.conf` policy
- document provisioning, access, and verification

## Non-Goals

- database replication
- PITR or WAL archiving
- public publication of PostgreSQL
- application schema deployment
- monitoring or exporter rollout for PostgreSQL

## Expected Repo Surfaces

- `inventory/hosts.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/postgres_guests.yml`
- `playbooks/postgres-vm.yml`
- `roles/postgres_vm`
- `docs/runbooks/configure-postgres-vm.md`
- `docs/adr/0025-dedicated-postgresql-vm-baseline.md`
- `workstreams.yaml`

## Expected Live Surfaces

- VM `150` running as `postgres-lv3` on `10.10.10.50`
- `postgresql` service enabled on the guest
- `nftables` enforcing deny-by-default inbound policy on the guest
- remote PostgreSQL access closed until client CIDRs are declared

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --syntax-check`
- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/postgres-vm.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm config 150'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 sudo systemctl status postgresql nftables --no-pager'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 sudo -u postgres psql -Atqc \"SHOW listen_addresses\"'`

## Merge Criteria

- guest provisioning inventory includes the PostgreSQL VM
- the PostgreSQL convergence playbook is idempotent
- the guest firewall and authentication policy are documented
- protected integration files remain untouched

## Notes For The Next Assistant

- remote database clients are intentionally blocked until `postgres_vm_client_allowed_sources` is populated
- do not add public DNS or ingress forwarding for PostgreSQL without a separate ADR
- do not bump `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` on this branch
- this workstream is branch-complete but not yet live-applied
