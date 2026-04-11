# Workstream ADR 0026: Dedicated PostgreSQL VM Baseline

- ADR: [ADR 0026](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0026-dedicated-postgresql-vm-baseline.md)
- Title: Dedicated PostgreSQL VM baseline
- Status: merged
- Branch: `codex/adr-0025-postgres-vm`
- Worktree: `../proxmox-host_server-postgres-vm`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `postgres`, `playbooks/postgres-vm.yml`, `roles/postgres_vm`, `roles/proxmox_tailscale_proxy`, `roles/hetzner_dns_record`

## Scope

- add a dedicated PostgreSQL guest to the Proxmox inventory
- converge a secure PostgreSQL baseline on that guest
- enforce a guest-local firewall and explicit `pg_hba.conf` policy
- expose PostgreSQL only through the Proxmox host Tailscale interface
- publish a tailnet-only DNS name for PostgreSQL access
- document provisioning, access, and verification

## Non-Goals

- database replication
- PITR or WAL archiving
- public publication of PostgreSQL
- HTTPS reverse proxying for PostgreSQL on the NGINX VM
- application schema deployment
- monitoring or exporter rollout for PostgreSQL

## Expected Repo Surfaces

- `inventory/hosts.yml`
- `inventory/host_vars/proxmox-host.yml`
- `playbooks/postgres-vm.yml`
- `playbooks/database-dns.yml`
- `roles/postgres_vm`
- `roles/hetzner_dns_record`
- `docs/runbooks/configure-postgres-vm.md`
- `docs/adr/0026-dedicated-postgresql-vm-baseline.md`
- `workstreams.yaml`

## Expected Live Surfaces

- VM `150` running as `postgres` on `10.10.10.50`
- `postgresql` service enabled on the guest
- `nftables` enforcing deny-by-default inbound policy on the guest
- TCP `5432` proxied from the Proxmox host Tailscale IP to the PostgreSQL VM
- `database.example.com` resolving to the Proxmox host Tailscale IPv4
- local peer administration available through `ops` and `postgres`

## Verification

- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/site.yml --syntax-check`
- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/postgres-vm.yml --syntax-check`
- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/database-dns.yml --syntax-check`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm config 150'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 sudo systemctl status postgresql nftables --no-pager'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 sudo -u postgres psql -Atqc \"SHOW listen_addresses\"'`
- `psql "host=database.example.com port=5432 dbname=postgres user=ops sslmode=prefer"`

## Merge Criteria

- guest provisioning inventory includes the PostgreSQL VM
- the PostgreSQL convergence playbook is idempotent
- the guest firewall and authentication policy are documented
- live verification confirms that PostgreSQL is reachable only through Tailscale
- protected integration files remain untouched

## Notes For The Next Assistant

- `database.example.com` is a Tailscale-only endpoint, not a public website
- do not add NGINX HTTPS publication for PostgreSQL itself
- this workstream was merged to `main` during integration because `0025` was already taken by the compose ADR series
- live apply completed on `2026-03-22` and the merged `main` line now reflects that state
