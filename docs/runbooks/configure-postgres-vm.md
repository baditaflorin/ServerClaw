# Configure PostgreSQL VM Runbook

## Purpose

This runbook captures the branch-level automation path for provisioning and hardening the dedicated PostgreSQL VM defined by ADR 0026.

## Managed VM

- `150` `postgres-lv3` `10.10.10.50`

## Security Model

- PostgreSQL is private-only and is not published through the NGINX edge.
- PostgreSQL is exposed only through a TCP proxy on the Proxmox host Tailscale IP on TCP `5432`.
- Guest packet filtering is enforced by the shared ADR 0067 network policy on both the Proxmox host and the guest-local `nftables` layer.
- SSH is limited to the declared guest-management source ranges.
- PostgreSQL TCP access on the guest is limited to the documented allow matrix, which currently permits the Proxmox host proxy path and `docker-runtime-lv3`.
- Local administration uses the Linux `ops` account plus a matching PostgreSQL role over peer authentication.
- `database.lv3.org` should resolve to the Proxmox host Tailscale IP, not the public NGINX edge.

## Repo Surfaces

- guest definition: [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- convergence playbook: [playbooks/postgres-vm.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/postgres-vm.yml)
- role defaults: [roles/postgres_vm/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/postgres_vm/defaults/main.yml)
- role contract note: [roles/postgres_vm/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/postgres_vm/README.md)
- DNS playbook: [playbooks/database-dns.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/database-dns.yml)

## Provision The VM

Clone or update the guest inventory on the Proxmox host:

```bash
ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 --tags guests
```

## Converge PostgreSQL And Guest Hardening

Use the Proxmox host jump path until direct private guest routing is the normal operator path:

```bash
make converge-postgres-vm
```

## Publish The Tailnet DNS Name

Use the Make target so the controller-local preflight runs before the DNS playbook:

```bash
HETZNER_DNS_API_TOKEN=... make database-dns
```

This creates or updates `database.lv3.org` so it resolves to the Proxmox host Tailscale IPv4.

## Connect To PostgreSQL

From a device that is already on the same tailnet:

```bash
psql "host=database.lv3.org port=5432 dbname=postgres user=ops sslmode=prefer"
```

For real remote use, replace `dbname` and `user` with an application-specific PostgreSQL role that has a password. The `ops` role is created primarily for local peer-authenticated administration on the VM.

For local administrative access on the VM itself:

```bash
ssh -J ops@100.118.189.95 ops@10.10.10.50
sudo -u postgres psql
```

## Verify

Confirm the VM exists on Proxmox:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm config 150'
```

Confirm the guest services are enabled:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 "sudo systemctl status postgresql nftables --no-pager"'
```

Confirm PostgreSQL is listening only on loopback and the guest private IP:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 "sudo -u postgres psql -Atqc \"SHOW listen_addresses\" && sudo ss -ltnp | grep 5432"'
```

Confirm the `ops` role exists for local peer administration:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.50 "sudo -u postgres psql -Atqc \"SELECT rolname, rolcreatedb, rolcreaterole, rolsuper FROM pg_roles WHERE rolname = '\''ops'\''\""'
```

Confirm that the DNS record resolves to the Proxmox host Tailscale IP:

```bash
dig +short database.lv3.org
```

Confirm that tailnet clients can reach PostgreSQL through the DNS name:

```bash
psql "host=database.lv3.org port=5432 dbname=postgres user=ops sslmode=prefer"
```

## Notes

- This runbook does not create application databases or passwords. Create those per workload and store secrets outside git.
- Backup coverage for the VM follows the shared Proxmox guest backup policy once ADR 0020 is applied live.
- Do not open public ingress for PostgreSQL from this runbook.
- Do not use the NGINX VM or `https://database.lv3.org` for raw PostgreSQL access. If a browser-based DB admin interface is needed later, treat that as a separate workstream.
