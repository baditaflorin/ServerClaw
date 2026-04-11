# Subdomain Governance

## Purpose

Keep `example.com` hostnames catalogued, validated, and provisioned through repo-managed automation instead of ad hoc DNS and edge edits.

## Canonical Sources

- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/service-capability-catalog.json`
- `roles/nginx_edge_publication/`
- `inventory/host_vars/proxmox-host.yml`

## Validation

Run the subdomain-specific checks directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
uvx --from pyyaml python scripts/subdomain_catalog.py --validate
uv run --with pyyaml python scripts/provider_boundary_catalog.py --validate
```

Run the full repository gate:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make validate
```

## Provision One Catalogued Hostname

Use the governed workflow only after the hostname already exists in `config/subdomain-catalog.json`.

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=ops.example.com
```

## Reconcile Governed DNS Drift

Use the ADR 0252 ledger workflow when the governed DNS drift set already exists
in the catalog and should be reconciled as one audited bundle instead of as a
single-hostname change:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
HETZNER_DNS_API_TOKEN=... make route-dns-assertion-ledger
```

## Exposure Audit

The governed catalog is now paired with a derived canonical publication registry
and live audit. That derived registry now includes route assertions and evidence
planning for DNS, zone state, HTTP auth, private routes, and TLS.

Use it after catalog or edge-routing changes:

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --write-registry
make subdomain-exposure-audit
```

See [subdomain exposure audit](subdomain-exposure-audit.md) for the full operator workflow and finding types.

What the target does:

- validates the catalog and checks that the selected FQDN is provisionable
- regenerates the canonical publication model plus delivery-adapter split used
  by shared consumers
- converges the DNS record through `roles/hetzner_dns_record`
- translates raw Hetzner provider payloads into canonical DNS facts before any matching or drift decisions are made
- if the FQDN already has a repo-managed edge route, re-runs `configure-edge-publication` so NGINX and the shared certificate set stay aligned
- if the governed change belongs to the ADR 0252 drift set, the dedicated
  `route-dns-assertion-ledger` workflow should be preferred over ad hoc single
  hostname edits

## Constraints

- `make provision-subdomain` is not a shortcut for inventing new hostnames outside the repo. The FQDN must already be declared in the catalog.
- Edge publication only works for hostnames that already have a repo-managed route definition through service topology or `public_edge_extra_sites`.
- Reserved first-label prefixes are enforced from the catalog. If a hostname uses a reserved prefix, it must be explicitly allowlisted in `reserved_prefixes`.
- Apex, tailnet-only, and other shared route assertions should be reconciled
  through the ADR 0252 ledger workflow once they are part of the governed drift
  set.

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
3. Remove the DNS record through the same managed workflow. Use
   `route-dns-assertion-ledger` when the hostname is already modeled in the ADR
   0252 governed drift set.
4. Delete the catalog entry only after the hostname is no longer expected anywhere in service or edge topology.
