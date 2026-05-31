# nginx_edge_publication

Publishes selected services and informational pages through the NGINX edge.

Inputs: ACME and certificate settings, static site definitions, and edge site publication definitions.
Outputs: rendered edge pages, NGINX site config, and a managed Let's Encrypt certificate.

## ACME challenge methods

Selected via `public_edge_acme_challenge_method`:

- `webroot` (default) — HTTP-01 served from the ACME web root. Cannot validate wildcard SANs.
- `dns-hetzner` — DNS-01 via the certbot Hetzner DNS plugin (legacy standalone DNS API, `dns.hetzner.com`). Fails with "token invalid (unauthorized)" for accounts that manage DNS via the Hetzner Cloud API.
- `dns-hetzner-cloud` (opt-in) — DNS-01 via a self-contained, stdlib-only certbot manual hook that talks to the Hetzner **Cloud** API (`api.hetzner.cloud/v1`), mirroring the `hetzner_dns_records` role. Required for wildcard certificates (e.g. `*.apps.example.com`) on Cloud-API accounts. No certbot plugin or virtualenv is installed; the role copies a hook script to the edge host and wires it as certbot's `--manual-auth-hook` / `--manual-cleanup-hook`. The hook appends (rather than overwrites) TXT values, so a SAN cert covering both `apps.example.com` and `*.apps.example.com` — which triggers two challenges at the same `_acme-challenge.apps` name — validates correctly.

### dns-hetzner-cloud variables (all defaulted)

- `public_edge_dns_hetzner_cloud_credentials_file` — credentials file written on the edge host (default `/etc/letsencrypt/hetzner-cloud.ini`); single line `hetzner_cloud_dns_api_token = <TOKEN>`.
- `public_edge_dns_hetzner_cloud_hook_path` — install path of the hook script on the edge host.
- `public_edge_dns_hetzner_cloud_propagation_seconds` — DNS propagation wait (default 60).

### Required environment variable

`HETZNER_DNS_API_TOKEN` is read from the controller environment and written to the credentials file on the edge host. For `dns-hetzner-cloud` this must be a Hetzner **Cloud** API token (the same token type used by the `hetzner_dns_records` role), not a legacy standalone DNS API token.
