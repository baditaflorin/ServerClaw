# ADR 0025: Dedicated PostgreSQL VM Baseline

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform now has a stable Proxmox host, a reusable Debian 13 template, non-root guest access, private guest networking, and a first set of infrastructure VMs.

It does not yet have a dedicated database tier.

Using PostgreSQL directly on the Proxmox host would mix data services with hypervisor responsibilities. Reusing the NGINX, Docker runtime, or build VMs for stateful database duties would also blur separation of concerns and weaken recovery boundaries.

The next database baseline needs to:

- introduce PostgreSQL as its own managed VM
- keep the service private to the internal network
- default to a deny-by-default guest firewall posture
- require strong password authentication for TCP clients
- preserve a secure non-root operator path
- fit the existing template-based guest provisioning and backup model

## Decision

We will manage PostgreSQL through a dedicated Debian 13 VM with these rules:

1. PostgreSQL runs on its own private Proxmox guest.
   - VMID: `150`
   - hostname: `postgres-lv3`
   - IPv4: `10.10.10.50`
2. The VM is provisioned from the shared Debian 13 cloud template and remains a normal managed guest in the existing `proxmox_guests` inventory.
3. PostgreSQL is installed from Debian packages on the guest.
   - The repository manages the guest baseline and PostgreSQL configuration.
   - This ADR does not introduce containers, Patroni, streaming replication, or external package repositories.
4. The database service remains private.
   - No public edge publication is added.
   - No host-level DNAT rule is added for PostgreSQL.
   - PostgreSQL listens only on loopback and the guest's private VM address.
5. Network access is deny-by-default on the guest.
   - `nftables` is enabled on the PostgreSQL VM.
   - inbound SSH is limited to declared management source ranges
   - inbound PostgreSQL is limited to an explicit client allowlist
   - an empty allowlist is valid and means remote clients stay blocked until deliberately opened
6. TCP client authentication uses SCRAM.
   - PostgreSQL is configured with `password_encryption = 'scram-sha-256'`
   - host-based access policy is managed explicitly through `pg_hba.conf`
7. Operator administration stays non-root by default.
   - Linux access continues through the `ops` user with sudo
   - a matching PostgreSQL role for `ops` is created for local peer-authenticated administration on the VM
   - break-glass database administration remains available through the local `postgres` account
8. The PostgreSQL VM becomes part of the managed backup scope once backup automation is applied live.
   - ADR 0020 already defines backup jobs from the `proxmox_guests` set
   - adding this VM to that managed guest list makes it eligible for the same backup policy without creating a separate backup mechanism

## Consequences

- Database service boundaries stay clear: hypervisor, edge, runtime, build, monitoring, and database duties remain separated.
- The guest firewall and `pg_hba.conf` make remote access explicit instead of relying on the private subnet alone.
- Operators get a secure local administration path without storing reusable superuser passwords in the repository.
- Application onboarding now requires a deliberate client allowlist update and explicit role creation, which is slower than ad hoc access but materially safer.
- High availability, replication, PITR tooling, TLS certificates for PostgreSQL clients, and exporter-based monitoring remain follow-up workstreams.

## Sources

- <https://www.postgresql.org/docs/current/runtime-config-connection.html>
- <https://www.postgresql.org/docs/current/auth-pg-hba-conf.html>
- <https://www.postgresql.org/docs/current/auth-password.html>
- <https://packages.debian.org/trixie/postgresql>
