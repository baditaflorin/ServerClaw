# postgres_vm

Applies the PostgreSQL guest baseline and firewall policy.

Inputs: package list, PostgreSQL service settings, listen addresses, admin role, and allowed source CIDRs.
Outputs: a configured PostgreSQL service, managed `pg_hba.conf`, and guest nftables rules.
