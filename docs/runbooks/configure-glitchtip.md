# Configure GlitchTip

This runbook covers the repo-managed GlitchTip deployment introduced by [ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md).

## Scope

The GlitchTip workflow converges:

- the GlitchTip runtime on `docker-runtime-lv3`
- the shared PostgreSQL backend role and database on `postgres-lv3`
- the public hostname `errors.lv3.org` on the shared NGINX edge
- the repo-managed Keycloak OIDC client used for browser sign-in
- the bootstrap admin, API token, and project-scoped DSN artifacts mirrored under `.local/glitchtip/`
- the alert-recipient wiring for Mattermost and ntfy on every repo-managed GlitchTip project

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- the mail-platform managed mailbox password exists at `.local/mail-platform/server-mailbox-password.txt`
- `HETZNER_DNS_API_TOKEN` is available when the edge certificate needs expansion

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-glitchtip
```

The target validates the public subdomain contract, refreshes the shared edge generated sites, and then converges PostgreSQL, Keycloak client wiring, the GlitchTip runtime, and the NGINX edge publication from one repo-managed entrypoint.

## Generated local artifacts

The workflow maintains controller-local artifacts under `.local/glitchtip/`:

- `database-password.txt`
- `secret-key.txt`
- `valkey-password.txt`
- `admin-password.txt`
- `api-token.txt`
- `projects.json`
- `mail-gateway.dsn`
- `windmill-jobs.dsn`
- `platform-findings-event-url.txt`

The workflow also mirrors the GlitchTip Keycloak client secret under `.local/keycloak/glitchtip-client-secret.txt`.

## Producer rollout

After the first GlitchTip bootstrap has created the DSN files, rerun producer converges that consume those DSNs:

```bash
HETZNER_DNS_API_TOKEN=... make converge-mail-platform
HETZNER_DNS_API_TOKEN=... make converge-windmill
```

`converge-mail-platform` injects the `mail-gateway.dsn` artifact into the live mail-gateway runtime. `converge-windmill` refreshes the repo-managed Windmill script set so the `windmill-jobs` GlitchTip project stays wired to the live automation path.

## Verification

Repository and syntax checks:

```bash
make syntax-check-glitchtip
uv run --with pytest python -m pytest -q tests/test_await_ansible_quiet.py tests/test_glitchtip_event.py tests/test_glitchtip_playbook.py tests/test_glitchtip_runtime_role.py
```

Runtime and publication verification:

```bash
curl -fsS https://errors.lv3.org/api/0/internal/health/
curl -fsS https://errors.lv3.org/_allauth/browser/v1/config | grep -E 'LV3 Keycloak|sso\.lv3\.org|openid-configuration'
python3 scripts/glitchtip_event_smoke.py \
  --base-url https://errors.lv3.org \
  --organization-slug lv3 \
  --api-token-file .local/glitchtip/api-token.txt \
  --dsn-file .local/glitchtip/platform-findings-event-url.txt \
  --timeout-seconds 300 \
  --request-timeout-seconds 60
```

A mail-gateway runtime that has been reconverged after GlitchTip bootstrap should also expose the Sentry runtime environment variables:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'docker exec mail-gateway env | grep -E "^SENTRY_(DSN|ENVIRONMENT|RELEASE)="'
```

The repo-managed publication verification now waits for a quiet controller window across `docker-runtime-lv3` and `nginx-lv3` before probing `errors.lv3.org`, and it retries once after that quiet window if another live apply had just been mutating the shared runtime or edge.

## Notes

- GlitchTip owns browser authentication itself through the repo-managed Keycloak OIDC client, so `errors.lv3.org` is published with `upstream_auth` instead of the shared edge oauth2-proxy boundary
- the public health endpoint and DSN store path remain reachable so SDKs, smoke checks, and publication probes can verify the live service end to end
- `.local/glitchtip/projects.json` is the canonical mirror of the repo-managed project catalogue and DSN outputs after each converge
- Hetzner's legacy `dns.hetzner.com` write API is in scheduled brownout during the DNS migration period. The DNS roles now retry provider payloads that report brownout inside an HTTP `200`, but a full `make converge-glitchtip` run can still fail on the localhost DNS record step while the provider window is active. In that case, rerun the converge after the brownout window instead of changing the service hosts by hand.
