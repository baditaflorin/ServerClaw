# Configure GlitchTip

This runbook covers the repo-managed GlitchTip deployment introduced by
[ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
and its Authentik cutover under
[ADR 0491](../adr/0491-authentik-for-operator-and-agent-sso.md).

## Scope

The GlitchTip workflow converges:

- the GlitchTip runtime on `docker-runtime`
- the shared PostgreSQL backend role and database on `postgres`
- the public hostname `errors.example.com` on the shared NGINX edge
- one selected generic `openid_connect` SocialApp, currently `provider_id=authentik`
- one healthy retained `provider_id=keycloak` SocialApp for per-client rollback
- the bootstrap admin, API token, and project-scoped DSN artifacts under
  `.local/glitchtip/`
- the alert-recipient wiring for Mattermost and ntfy

The GlitchTip playbook does not converge either identity provider. The selected
Authentik application/provider must exist before GlitchTip runs. The prior
Keycloak client secret remains a separate rollback artifact and is never
overwritten by Authentik reconciliation.

## Preconditions

- select the intended identity and topology explicitly; the converge refuses
  shared `.local/` defaults because they may describe another deployment:

  ```bash
  export PLATFORM_IDENTITY_OVERLAY=/absolute/path/to/identity.yml
  export PLATFORM_TOPOLOGY_OVERLAY=/absolute/path/to/topology.yml
  LOCAL_ROOT="$(scripts/resolve_local_overlay_root.sh)"
  IDENTITY_FILE="${PLATFORM_IDENTITY_OVERLAY:?select the intended deployment identity}"
  TOPOLOGY_FILE="${PLATFORM_TOPOLOGY_OVERLAY:?select the intended deployment topology}"
  case "${IDENTITY_FILE}" in
    /*) ;;
    .local/*) IDENTITY_FILE="${LOCAL_ROOT}/${IDENTITY_FILE#.local/}" ;;
    *) IDENTITY_FILE="${LOCAL_ROOT}/${IDENTITY_FILE}" ;;
  esac
  case "${TOPOLOGY_FILE}" in
    /*) ;;
    .local/*) TOPOLOGY_FILE="${LOCAL_ROOT}/${TOPOLOGY_FILE#.local/}" ;;
    *) TOPOLOGY_FILE="${LOCAL_ROOT}/${TOPOLOGY_FILE}" ;;
  esac
  export PLATFORM_IDENTITY_OVERLAY="${IDENTITY_FILE}"
  export PLATFORM_TOPOLOGY_OVERLAY="${TOPOLOGY_FILE}"
  PLATFORM_DOMAIN="$(uv run --no-project --with pyyaml python -c \
    'import pathlib,sys,yaml; print(yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["platform_domain"])' \
    "${IDENTITY_FILE}")"
  KEYCLOAK_REALM="${KEYCLOAK_REALM:-${PLATFORM_DOMAIN%%.*}}"
  ```

  Leave `PLATFORM_INVENTORY_OVERLAY` unset to use the committed private
  inventory. Set it only when an intentional alternate inventory has been
  reviewed alongside these selectors.

- `make preflight-glitchtip-deployment-selection env=production` passes, proving the selected
  identity and topology reproduce tracked `platform_generation` facts and the
  selected inventory resolves the declared GlitchTip, PostgreSQL, and edge
  target hosts before DNS or runtime mutation
- `bootstrap_ssh_private_key` is present under `${LOCAL_ROOT}/ssh/`
- the separately approved
  `make bootstrap-openbao-runtime-secret-provisioner env=production` workflow has generated
  `${LOCAL_ROOT}/openbao/runtime-secret-provisioner-approle.json` and
  `${LOCAL_ROOT}/openbao/runtime-secret-provisioner-bootstrap-receipt.json`
- both provisioner artifacts are non-empty regular `0600` files; the receipt is
  emitted only after provisioner login plus exact allow/deny capability checks
- the OpenBao init payload, bootstrap root token, and controller automation
  AppRole are not accepted as substitutes; do not run `converge-openbao` to
  satisfy this gate because it may restart or unseal against stale bootstrap
  state
- the mail-platform managed mailbox password exists at
  `${LOCAL_ROOT}/mail-platform/server-mailbox-password.txt`
- the Authentik provider declaration in `config/authentik/oauth-clients.yaml`
  uses the same public client ID as `glitchtip_oidc_client_id`
- `${LOCAL_ROOT}/authentik/glitchtip-client-secret.txt` exists
- `${LOCAL_ROOT}/keycloak/glitchtip-client-secret.txt` is preserved for rollback
- Authentik registers this backend callback exactly:
  `https://errors.example.com/accounts/oidc/authentik/login/callback/`
- `HETZNER_DNS_API_TOKEN` is available when the edge certificate needs expansion

The selected issuer is stored without a trailing slash:
`https://id.example.com/application/o/glitchtip`. GlitchTip's allauth provider
adds `/.well-known/openid-configuration`; a trailing slash in the stored issuer
would produce a double-slash discovery URL.

## Converge

Run:

```bash
make preflight-glitchtip-deployment-selection env=production
make bootstrap-openbao-runtime-secret-provisioner env=production
HETZNER_DNS_API_TOKEN=... make converge-glitchtip env=production
```

The GlitchTip target repeats the explicit identity/topology guard, then
preflight checks the narrow OpenBao provisioner artifact, both
provider-specific client-secret artifacts, and the retained Keycloak public
discovery endpoint. Only after those checks pass does it validate the public
subdomain contract, refresh the shared edge generated sites, and converge
PostgreSQL, GlitchTip, and NGINX publication. It does not modify Authentik,
Keycloak, or OpenBao.

The runtime role reconciles both the selected and rollback SocialApps
transactionally by `provider` plus `provider_id`, updates their non-secret
metadata and provider-specific client credentials, links them to the managed
organization, and collapses duplicate rows for each provider. Keeping the
rollback metadata healthy is required: GlitchTip resolves every SocialApp when
serving `/api/settings/`, so one stale provider can hide all OIDC buttons even
when the selected Authentik headless redirect is healthy.

The compose template uses the shared `hairpin_hosts()` mapping. This is required
because GlitchTip fetches OIDC discovery server-side; a container that resolves
`id.example.com` to the public edge may otherwise fail on a non-hairpin-capable
route even while the endpoint works from an operator workstation.

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

The selected Authentik client artifacts and preserved Keycloak rollback secret
remain in their provider-specific `.local/` directories; they are not copied
into Git or rendered into receipts.

## Producer rollout

After the first bootstrap creates the DSN files, rerun producers that consume
those DSNs:

```bash
HETZNER_DNS_API_TOKEN=... make converge-mail-platform
HETZNER_DNS_API_TOKEN=... make converge-windmill
```

## Verification

Repository and syntax checks:

```bash
make syntax-check-glitchtip
uv run --with pytest python -m pytest -q \
  tests/test_glitchtip_oidc_smoke.py \
  tests/test_glitchtip_event.py \
  tests/test_glitchtip_playbook.py \
  tests/test_glitchtip_runtime_role.py
python3 scripts/validate_integrations.py --check-dead
```

Runtime and publication verification:

```bash
curl -fsS "https://errors.${PLATFORM_DOMAIN}/api/0/internal/health/"
python3 scripts/glitchtip_oidc_smoke.py \
  --base-url "https://errors.${PLATFORM_DOMAIN}" \
  --provider-id authentik \
  --issuer-url "https://id.${PLATFORM_DOMAIN}/application/o/glitchtip" \
  --expected-client-id glitchtip \
  --callback-url "https://errors.${PLATFORM_DOMAIN}/login" \
  --client-secret-file "${LOCAL_ROOT}/authentik/glitchtip-client-secret.txt"
python3 scripts/glitchtip_event_smoke.py \
  --base-url "https://errors.${PLATFORM_DOMAIN}" \
  --organization-slug lv3 \
  --api-token-file "${LOCAL_ROOT}/glitchtip/api-token.txt" \
  --dsn-file "${LOCAL_ROOT}/glitchtip/platform-findings-event-url.txt" \
  --timeout-seconds 300 \
  --request-timeout-seconds 60
curl --fail --silent --show-error \
  "https://sso.${PLATFORM_DOMAIN}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration" \
  >/dev/null
```

GlitchTip uses django-allauth in headless-only mode. A GET to
`/accounts/oidc/authentik/login/` therefore returns 404 by design and is not a
valid login smoke. The supported flow is a synchronous browser POST to
`/_allauth/browser/v1/auth/provider/redirect`. The smoke script obtains the
CSRF cookie from the public config endpoint, submits that form without user
credentials, refuses to follow the resulting redirect, and validates only its
non-secret authorization endpoint, client binding, state presence, and backend
callback. With `--client-secret-file`, it also submits a deliberately invalid
authorization code twice and proves that Authentik accepts the selected client
secret before returning `invalid_grant`, while rejecting a random secret as
`invalid_client`. The secret value is read from the `0600` file and is never
printed.

### Mandatory interactive browser gate

The redirect and token probes do not prove that a human can complete the full
session lifecycle. Before this workstream may advance to Outline, use a clean
browser profile and record all three results in the governed GlitchTip
live-apply receipt:

1. Open `https://errors.${PLATFORM_DOMAIN}/login`, choose the Authentik
   provider, and authenticate with an approved existing verification identity.
2. Confirm the browser returns to GlitchTip and that an authenticated page for
   the expected account and `lv3` organization loads successfully.
3. Sign out through the GlitchTip UI and confirm the same browser context can no
   longer access the authenticated page without starting a new login.

Record timestamps, the non-secret account identifier, the final origins, and
pass/fail results. Do not record passwords, cookies, CSRF values, OAuth state,
authorization codes, token responses, or credential-bearing screenshots. A
successful redirect-only smoke is not a substitute for this gate, and Outline
remains blocked until the login, session, and logout evidence is present.

The converge also requires `/api/settings/` to return HTTP 200 and advertise
both Authentik and the retained Keycloak rollback provider with resolved
authorization URLs. This protects the actual login page from a stale rollback
issuer that would otherwise make the frontend settings request fail closed.
The edge CSP must likewise permit `form-action` to the selected Authentik and
rollback Keycloak origins. GlitchTip begins OIDC with a same-origin allauth form
POST, but browsers enforce `form-action` across its external 302 redirect; a
`'self'`-only policy leaves both buttons visible while silently blocking login.

`scripts/resolve_local_overlay_root.sh` makes these token-file and DSN-file
arguments work from both the primary checkout and linked worktrees. Do not
replace them with worktree-relative `.local/` paths.

## Per-client rollback

Keep Authentik and Keycloak live in parallel throughout ADR 0491. If the
Authentik redirect or token exchange fails:

1. Preserve the failed Authentik metadata and logs without recording secrets.
2. Select the prior Keycloak provider metadata and the existing
   `${LOCAL_ROOT}/keycloak/glitchtip-client-secret.txt` through an explicitly
   reviewed role override or integration change.
3. Reconcile only GlitchTip and repeat the headless redirect plus event smokes.
4. Re-probe the retained Keycloak public discovery endpoint; secret-file
   presence alone is not rollback-health evidence.
5. Do not decommission Authentik or Keycloak as part of this per-client rollback.

## Notes

- GlitchTip owns browser authentication; the edge does not add oauth2-proxy.
- Public health and DSN ingestion remain reachable for SDK and smoke traffic.
- `${LOCAL_ROOT}/glitchtip/projects.json` is the canonical controller mirror of the
  repo-managed project catalog and DSN outputs.
- Never print client secrets, CSRF values, OAuth state, authorization query
  strings, rendered runtime environments, or credential-bearing callback URLs.
