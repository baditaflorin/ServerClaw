# Restore shared Authentik-protected edge sign-in

- ADR: 0491
- Status: in progress
- Branch: `codex/authentik-edge-oidc-recovery-20260930`
- Worktree: `.worktrees/authentik-edge-oidc-recovery-20260930`
- Depends on: `ws-0512-authentik-consumer-e2e`

## Scope

Restore the shared OAuth2 proxy used by NGINX-protected services, then verify
that unauthenticated users are redirected to Authentik and authorized users
reach the intended service session. Preserve the Authentik access gate and the
existing least-privilege group policy.

## Findings

On 2026-09-30, `repo-intake` and `ops-portal` returned HTTP 500 at the public
edge while both application containers and their internal health checks were
healthy. NGINX logs showed its `auth_request` subrequest failing because the
local OAuth2 proxy was not listening on its configured loopback port.

The proxy config validated and named the Authentik issuer correctly, but its
startup OIDC discovery tried the public issuer address from the edge host and
was refused by the network's lack of hairpin routing. Pinning the issuer
hostname to the local NGINX edge returned the discovery document with valid
TLS. The managed `public_edge_oidc_auth` role already declares this host
mapping; it was absent from the live `/etc/hosts` file.

The live recovery used a credential-preserving Ansible path: it repaired the
issuer mapping, restarted the existing proxy, and verified the proxy auth
endpoint without rendering or reading OAuth client credentials. A corrected
ignored local inventory overlay now includes the verified management gateway,
so the persistent firewall retains operator access after a reload. The earlier
interrupted broad converge is fully superseded by this managed firewall apply.

## Apply and verification

The `configure-edge-publication` workflow preflight passed, and the scoped
production apply ran under the VM apply lock through the governed Make target.
The scoped tags applied only the guest firewall and recovery-only OIDC tasks;
they did not render proxy credentials or publish NGINX configuration.

Completed live checks on 2026-09-30, without printing credentials, cookies,
OAuth state, authorization codes, or environment files:

1. The managed host mapping resolves the issuer through the local edge; OIDC
   discovery returned HTTP 200.
2. The proxy is active with zero restarts at follow-up, and its unauthenticated
   auth endpoint returns the expected HTTP 401.
3. Repository Intake and Ops Portal both redirect through the OAuth2 sign-in
   path, produce an authorization-code request with the expected client and
   callback host, and reach Authentik's default login flow (HTTP 200), rather
   than a 5xx.
4. The persistent and active guest firewall both include the verified
   management gateway, and SSH remained reachable after the firewall reload.

Still pending: a credentialed fresh-browser callback/session/logout round trip
and a non-admin group-denial result. The existing non-admin `gitea-e2e` browser
harness was attempted twice but stayed on Authentik's default login flow and
did not reach the shared-proxy callback; its sanitized output does not prove
either a denial or successful login. Do not retry blindly or widen its groups.
The operator's credentials were not used or exposed. The local OAuth
client-secret artifact required by the full configuration-rendering role is
absent, so this recovery intentionally preserved the deployed proxy config
instead of retrieving, copying, rotating, or rendering credentials.

Gitea, Harbor, Grafana, Outline, GlitchTip, and Chat retain separate consumer
verification tracks; this edge recovery does not mark those integrations done.

The separate Authentik consumer workstream remains blocked on the existing
Grafana role, Outline realtime, and GlitchTip provisioning security gates. This
workstream does not bypass those gates or claim those consumer issues are fixed.

## Session notes

- Plane synchronization was attempted; the configured Plane API token was
  rejected. Git workstream files remain authoritative until Plane access is
  repaired.
- The full repository preflight, generated certificate catalog/admission,
  portal builds, and published-artifact secret scans passed. Certificate
  validation reported two private-only endpoint timeouts unrelated to public
  edge TLS; the other 46 hostnames validated.
- The generated operations-portal snapshot is intentionally excluded from this
  branch unless a reviewed, deployment-neutral source change requires it.
