# ws-provision-operator-localize — Localize provision_operator.py

**ADR:** 0318 (operator provisioning) · **Status:** ready

## Problem

`scripts/provision_operator.py` is the one-shot operator-onboarding tool: it
creates a Keycloak user, mints a Headscale pre-auth key, and emails the new
operator their SSO credentials, the service catalog, and an SSH/VPN tutorial.

It still carries the pre-migration **generic placeholders** and never adopted
the ADR-0385/0407 identity-derivation pattern the rest of the platform uses:

- `REALM = "lv3"` — the live realm is `platform_domain.split('.')[0]`; `lv3`
  no longer exists (returns 404), so user creation fails outright.
- Admin identifiers `lv3-bootstrap-admin` / `lv3-admin-runtime` are hardcoded;
  the live names derive from `platform_identity.config_prefix`.
- `*.localhost` for Keycloak, Headscale and step-ca; the real endpoints are
  `sso.<domain>`, `headscale.<domain>`, `ca.<domain>`.
- The welcome email's `PLATFORM SERVICES` block is a stale hand-maintained list
  (Outline/Vikunja/Mattermost on `*.localhost`) divorced from the real catalog.
- A fixed SMTP relay (`10.10.10.20:587`) that doesn't match the deployment and
  points at a docker-internal Stalwart hostname unreachable from the SSH proxy.

## Approach (ADR 0407 — generic by default)

No deployment-specific literals enter the committed script. Everything is
derived at runtime from inventory + the `.local` identity overlay, with env
overrides preserved:

1. Resolve `platform_domain` / `config_prefix` via
   `scripts/identity_yaml.load_identity_vars()`; derive `realm =
   platform_domain.split('.')[0]` and admin ids `<prefix>-bootstrap-admin` /
   `<prefix>-admin-runtime`.
2. Derive endpoint URLs from the domain (`sso.`, `headscale.`, `ca.`), keeping
   the existing `LV3_*_URL` env overrides.
3. Build the email service list from `config/service-capability-catalog.json`
   (public entries), substituting `example.com` → real domain, grouped by the
   catalog `category`.
4. Send through the documented mail-gateway HTTP API
   (`service_url("mail_platform") + /send`, `platform-transactional` gateway
   key) via the SSH proxy, instead of the broken smtplib-to-docker-hostname
   path.

## Verification

- `python3 scripts/provision_operator.py … --dry-run` renders real-domain
  values (realm, endpoints, service list) from the local overlay.
- `python3 -c "import ast; ast.parse(open('scripts/provision_operator.py').read())"`
- The committed file contains no `0mcp`/`0mcp.com` literals.
