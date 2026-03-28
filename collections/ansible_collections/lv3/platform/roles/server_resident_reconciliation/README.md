# server_resident_reconciliation

Bootstraps and maintains the Proxmox host's server-resident `ansible-pull` reconcile loop.

The controller-driven bootstrap step can create a least-privilege Gitea read token and mirror it to the host. Recurring host-local runs reuse only the mirrored host token, not the controller-side admin token.

The role also renders a dedicated local inventory for `ansible-pull` so the
checkout step can target `localhost` while the playbook still limits to the
durable `proxmox_florin` alias.
