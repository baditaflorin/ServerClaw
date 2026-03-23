# Subdomain Governance

## Purpose

Keep `lv3.org` hostnames catalogued, validated, and provisioned through repo-managed automation instead of ad hoc DNS and edge edits.

## Canonical Sources

- `config/subdomain-catalog.json`
- `config/service-capability-catalog.json`
- `roles/nginx_edge_publication/`
- `inventory/host_vars/proxmox_florin.yml`

## Validation

Run the subdomain-specific checks directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/subdomain_catalog.py --validate
```

Run the full repository gate:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make validate
```

## Provision One Catalogued Hostname

Use the governed workflow only after the hostname already exists in `config/subdomain-catalog.json`.

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=ops.lv3.org
```

What the target does:

- validates the catalog and checks that the selected FQDN is provisionable
- converges the DNS record through `roles/hetzner_dns_record`
- if the FQDN already has a repo-managed edge route, re-runs `configure-edge-publication` so NGINX and the shared certificate set stay aligned

## Constraints

- `make provision-subdomain` is not a shortcut for inventing new hostnames outside the repo. The FQDN must already be declared in the catalog.
- Edge publication only works for hostnames that already have a repo-managed route definition through service topology or `public_edge_extra_sites`.
- Reserved first-label prefixes are enforced from the catalog. If a hostname uses a reserved prefix, it must be explicitly allowlisted in `reserved_prefixes`.

## Lifecycle

### Create

1. Add or update the owning service in `config/service-capability-catalog.json`.
2. Add the FQDN to `config/subdomain-catalog.json`.
3. If the hostname should be routed through NGINX, add or update the repo-managed edge route definition.
4. Run `make validate`.
5. Run `HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=<hostname>`.

### Retire

1. Mark the catalog entry `status: retiring`.
2. Remove or redirect the repo-managed edge route if one exists.
3. Remove the DNS record through the same managed workflow.
4. Delete the catalog entry only after the hostname is no longer expected anywhere in service or edge topology.
