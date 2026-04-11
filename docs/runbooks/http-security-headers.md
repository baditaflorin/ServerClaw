# HTTP Security Headers

## Purpose

Use the repo-managed public edge header policy to verify that every published hostname serves the hardened browser protections defined in ADR 0136.

## Repo-Managed Inputs

- Role defaults: [collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml)
- Edge template: [collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2)
- Audit tool: [scripts/security_headers_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/security_headers_audit.py)

## Verify From The Repo

Run the full audit against every edge-published hostname:

```bash
make security-headers-audit
```

Audit a single hostname while iterating on a CSP override:

```bash
uv run --with pyyaml python scripts/security_headers_audit.py --host docs.example.com
```

## Verify A Live Response Manually

Spot-check the response headers from outside the platform:

```bash
curl -sSI https://docs.example.com/ | rg 'Strict-Transport-Security|Content-Security-Policy|X-Frame-Options|X-Content-Type-Options|Referrer-Policy|Permissions-Policy|X-Robots-Tag'
```

## When To Change The Policy

- Adjust `public_edge_security_headers_overrides` when a specific published app needs a narrower or broader CSP than the global default.
- Keep the global policy strict and document each relaxed directive in ADR 0136.
- Re-run the audit after every public-edge change and after upgrades to Grafana, Keycloak, Uptime Kuma, MkDocs, or the ops portal.
