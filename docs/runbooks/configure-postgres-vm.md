# Configure PostgreSQL VM Runbook

## Purpose

This runbook captures the branch-level automation path for provisioning and hardening the dedicated PostgreSQL VM defined by ADR 0025.

## Managed VM

- `150` `postgres-lv3` `10.10.10.50`

## Security Model

- PostgreSQL is private-only and is not published through the NGINX edge.
- PostgreSQL is exposed only through a TCP proxy on the Proxmox host Tailscale IP on TCP `5432`.
- The guest runs its own `nftables` policy with default-drop inbound behavior.
- SSH is limited to the declared management source ranges.
- PostgreSQL TCP access on the guest is limited to the Proxmox host internal gateway `10.10.10.1/32`, because the host-side Tailscale proxy terminates client connections and opens the upstream connection itself.
- Local administration uses the Linux `ops` account plus a matching PostgreSQL role over peer authentication.
- `database.lv3.org` should resolve to the Proxmox host Tailscale IP, not the public NGINX edge.

## Repo Surfaces

- guest definition: [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- Postgres host group variables: [inventory/group_vars/postgres_guests.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/postgres_guests.yml)
- convergence playbook: [playbooks/postgres-vm.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/postgres-vm.yml)
- DNS playbook: [playbooks/database-dns.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/database-dns.yml)

## Provision The VM

Clone or update the guest inventory on the Proxmox host:

```bash
ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 --tags guests
```

## Converge PostgreSQL And Guest Hardening

Use the Proxmox host jump path until direct private guest routing is the normal operator path:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/postgres-vm.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Publish The Tailnet DNS Name

Run the DNS playbook with a Hetzner DNS API token:

```bash
HETZNER_DNS_API_TOKEN=... ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/database-dns.yml
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
