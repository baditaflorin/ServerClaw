# Configure Plausible

This runbook covers the repo-managed Plausible Analytics deployment introduced by [ADR 0283](../adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md).

## Scope

The Plausible workflow converges:

- the Plausible Community Edition runtime on `docker-runtime-lv3`
- the public hostname `analytics.lv3.org` on the shared NGINX edge
- the repo-managed bootstrap user retained for recovery and verification
- the declared public site-registration list used for tracker injection and analytics seeding
- the canonical `ops.lv3.org` site registration used by ADR 0316 journey analytics for private operator flows
- the public tracker and health allowlist on the shared edge while the dashboard UI remains protected by the existing edge OIDC flow

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- the mail-platform managed mailbox password exists at `.local/mail-platform/server-mailbox-password.txt`
- `HETZNER_DNS_API_TOKEN` is available when the edge certificate needs expansion

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-plausible
```

The target validates the public subdomain contract and refreshes the shared
`build/changelog-portal/` and `build/docs-portal/` artifacts before publishing
`analytics.lv3.org` through the edge, so a fresh worktree does not need a
separate portal/docs generation step.

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/plausible/`:

- `bootstrap-user-password.txt`
- `database-password.txt`
- `secret-key-base.txt`

## Verification

Repository and syntax checks:

```bash
make syntax-check-plausible
```

Runtime and public verification:

```bash
curl -fsS https://analytics.lv3.org/api/health
curl -I https://analytics.lv3.org/
curl -fsS https://nginx.lv3.org/ | grep -F 'https://analytics.lv3.org/js/script.js'
curl -fsS \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (LV3 Plausible Smoke)' \
  -d '{"name":"pageview","url":"https://nginx.lv3.org/plausible-smoke","domain":"nginx.lv3.org"}' \
  https://analytics.lv3.org/api/event
curl -fsS \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (LV3 Journey Smoke)' \
  -d '{"name":"pageview","url":"https://ops.lv3.org/journeys/operator-access-admin/start","domain":"ops.lv3.org","props":{"surface":"operator_access_admin","event_type":"journey_smoke"}}' \
  https://analytics.lv3.org/api/event
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  ops@10.10.10.20 \
  'sudo docker exec plausible bin/plausible rpc "import Ecto.Query; site = Plausible.Sites.get_by_domain!(\"nginx.lv3.org\"); seen = Plausible.ClickhouseRepo.exists?(from e in \"events_v2\", where: e.site_id == ^site.id and e.pathname == ^\"/plausible-smoke\"); IO.puts(Jason.encode!(%{seen: seen}))"'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  ops@10.10.10.20 \
  'sudo docker exec plausible bin/plausible rpc "import Ecto.Query; site = Plausible.Sites.get_by_domain!(\"ops.lv3.org\"); seen = Plausible.ClickhouseRepo.exists?(from e in \"events_v2\", where: e.site_id == ^site.id and e.pathname == ^\"/journeys/operator-access-admin/start\"); IO.puts(Jason.encode!(%{seen: seen}))"'
```

The last command verifies that one synthetic event has reached Plausible's ClickHouse-backed event store for the seeded `nginx.lv3.org` site.

## Notes

- Plausible Community Edition is deployed here without the enterprise-only service-native SSO path, so the dashboard is protected by the shared NGINX edge oauth2-proxy/Keycloak boundary instead of an application-owned identity client
- the repo-managed bootstrap Plausible user remains intentionally available as a break-glass recovery and verification identity even though normal browser access goes through the shared edge sign-in path
- only the explicit `plausible_site_registrations` list is tracked; ADR 0316 intentionally reuses that allowlist by emitting canonical `ops.lv3.org` journey URLs from the private Windmill operator surface instead of trying to register a private `100.64.0.1:8005` site
