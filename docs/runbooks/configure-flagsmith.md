# Configure Flagsmith

This runbook covers the repo-managed Flagsmith deployment introduced by [ADR 0288](../adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md).

## Scope

The Flagsmith workflow converges:

- the shared PostgreSQL role and `flagsmith` database on `postgres-lv3`
- the Flagsmith Community Edition runtime on `docker-runtime-lv3`
- the public hostname `flags.lv3.org` on the shared NGINX edge
- the repo-managed baseline org, project, environment, and feature seed state
- the controller-local mirrored environment API keys stored under `.local/flagsmith/`

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- `HETZNER_DNS_API_TOKEN` is available when the edge certificate needs expansion

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-flagsmith
```

The target validates the subdomain exposure contract and refreshes the shared
generated edge static sites before publishing `flags.lv3.org`, so a fresh
worktree does not need a separate docs or portal generation step first.

To exercise the full repository wrapper path, run:

```bash
ALLOW_IN_PLACE_MUTATION=true HETZNER_DNS_API_TOKEN=... make live-apply-service service=flagsmith env=production
```

That wrapper runs `check-canonical-truth` before the service replay. On an
isolated workstream branch it may stop on a stale shared `README.md` or other
protected canonical-truth surface. Keep those shared writes for the exact-main
integration step, and use `make converge-flagsmith` as the service-specific
live replay path while protected release and README updates are intentionally
out of scope on the workstream branch.

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/flagsmith/`:

- `database-password.txt`
- `django-secret-key.txt`
- `admin-password.txt`
- `environment-keys.json`

## Verification

Repository and syntax checks:

```bash
make syntax-check-flagsmith
```

Runtime and public verification:

```bash
curl -fsS https://flags.lv3.org/health
curl -I https://flags.lv3.org/
curl -I https://flags.lv3.org/api/v1/projects/
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8017/health'
```

## Notes

- Flagsmith Community Edition is published behind the shared edge oauth2-proxy and Keycloak boundary; this workflow does not rely on a Flagsmith-local OIDC client.
- The public `/health` endpoint intentionally remains reachable without browser sign-in so external probes and role verification can confirm the edge path.
- Client environment API keys are mirrored into `.local/flagsmith/environment-keys.json` and written to OpenBao at `services/flagsmith/environment-keys`; consume them from OpenBao rather than committing or hardcoding them.
