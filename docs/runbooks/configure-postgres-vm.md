# Configure PostgreSQL VM Runbook

## Purpose

This runbook captures the branch-level automation path for provisioning and hardening the managed PostgreSQL guests defined by ADR 0026 and the ADR 0359 declarative client registry.

## Managed Guests

- `150` `postgres` `10.10.10.50`
- `154` `postgres-replica` `10.10.10.51`
- `151` `postgres-apps` `10.10.10.52`
- `152` `postgres-data` `10.10.10.54`

## Security Model

- PostgreSQL is private-only and is not published through the NGINX edge.
- PostgreSQL is exposed only through a TCP proxy on the Proxmox host Tailscale IP on TCP `5432`.
- Guest packet filtering is enforced by the shared ADR 0067 network policy on both the Proxmox host and the guest-local `nftables` layer.
- SSH is limited to the declared guest-management source ranges.
- PostgreSQL TCP access on the guest is limited by `inventory/group_vars/platform_postgres.yml`, which renders per-service `pg_hba.conf` entries and keeps only Docker bridge CIDR fallbacks (`172.16.0.0/12`, `192.168.0.0/16`, `10.200.0.0/16`).
- Local administration uses the Linux `ops` account plus a matching PostgreSQL role over peer authentication.
- `database.example.com` should resolve to the Proxmox host Tailscale IP, not the public NGINX edge.

## Repo Surfaces

- guest definitions: `inventory/host_vars/proxmox-host.yml`
- registry: `inventory/group_vars/platform_postgres.yml`
- guest-scoped PostgreSQL defaults: `inventory/group_vars/postgres_guests.yml`
- convergence playbook: `playbooks/postgres-vm.yml`
- governed live-apply wrapper: `playbooks/services/postgres-vm.yml`
- role: `collections/ansible_collections/lv3/platform/roles/postgres_vm/`
- DNS playbook: `playbooks/database-dns.yml`

## Provision The Guests

Provision or reconcile the managed PostgreSQL guests from inventory:

```bash
make provision-guests env=production EXTRA_ARGS='-e proxmox_guest_ssh_connection_mode=proxmox_host_jump'
```

## Converge PostgreSQL And Guest Hardening

Use the Proxmox host jump path until direct private guest routing is the normal operator path:

```bash
make live-apply-service service=postgres-vm env=production EXTRA_ARGS='-e proxmox_guest_ssh_connection_mode=proxmox_host_jump'
```

## Publish The Tailnet DNS Name

Use the Make target so the controller-local preflight runs before the DNS playbook:

```bash
HETZNER_DNS_API_TOKEN=... make database-dns
```

This creates or updates `database.example.com` so it resolves to the Proxmox host Tailscale IPv4.

ADR 0098 defines a future PostgreSQL HA VIP, but its
`Implemented In Platform Version` remains `not yet`. Until that live cutover is
performed, the governed truth for `database.example.com` remains the Proxmox host
Tailscale proxy and ADR 0252 verifies that publication.

## Connect To PostgreSQL

From a device that is already on the same tailnet:

```bash
psql "host=database.example.com port=5432 dbname=postgres user=ops sslmode=prefer"
```

For real remote use, replace `dbname` and `user` with an application-specific PostgreSQL role that has a password. The `ops` role is created primarily for local peer-authenticated administration on the VM.

For local administrative access on the VM itself:

```bash
ssh -J ops@100.64.0.1 ops@10.10.10.50
sudo -u postgres psql
```

## Verify

Confirm the managed guests exist on Proxmox:

```bash
ssh -i .local/ssh/bootstrap.id_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo qm status 150; sudo qm status 151; sudo qm status 152; sudo qm status 154'
```

Confirm the guest services are enabled:

```bash
ansible -i inventory/hosts.yml 'postgres:postgres-replica:postgres-apps:postgres-data' \
  -m shell -a "systemctl is-active postgresql nftables" \
  --private-key .local/ssh/bootstrap.id_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Confirm PostgreSQL is listening only on loopback and the guest private IP:

```bash
ansible -i inventory/hosts.yml postgres \
  -m shell -a "sudo -u postgres psql -Atqc \"SHOW listen_addresses\" && ss -ltnp | grep 5432" \
  --private-key .local/ssh/bootstrap.id_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Confirm the per-service registry entries exist in `pg_hba.conf`:

```bash
ansible -i inventory/hosts.yml postgres \
  -m shell -a "sudo grep -nE 'host\\s+(keycloak|windmill)\\s+(keycloak|windmill_admin)' /etc/postgresql/*/main/pg_hba.conf" \
  --private-key .local/ssh/bootstrap.id_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Confirm that intended service logins succeed and cross-database logins fail:

```bash
ssh -i .local/ssh/bootstrap.id_ed25519 -o IdentitiesOnly=yes -o ProxyJump=ops@100.64.0.1 ops@10.10.10.20
ssh -i .local/ssh/bootstrap.id_ed25519 -o IdentitiesOnly=yes -o ProxyJump=ops@100.64.0.1 ops@10.10.10.92
```

Use `psql` from `docker-runtime` and `runtime-control` with the controller-local password material for representative services, then confirm an unintended login such as `keycloak -> windmill` returns `no pg_hba.conf entry`.

Confirm that the DNS record resolves to the Proxmox host Tailscale IP:

```bash
dig +short database.example.com
```

Confirm that tailnet clients can reach PostgreSQL through the DNS name:

```bash
psql "host=database.example.com port=5432 dbname=postgres user=ops sslmode=prefer"
```

## Notes

- This runbook does not replace the ADR 0098 / ADR 0218 HA orchestration path; it covers the managed `postgres-vm` baseline and ADR 0359 access policy on the current guests.
- Application database credentials remain controller-local secrets under `.local/`.
- Backup coverage for the VM follows the shared Proxmox guest backup policy once ADR 0020 is applied live.
- Do not open public ingress for PostgreSQL from this runbook.
- Do not use the NGINX VM or `https://database.example.com` for raw PostgreSQL access. If a browser-based DB admin interface is needed later, treat that as a separate workstream.
