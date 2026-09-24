# Grafana Authentik reachability

## Scope

Repair Grafana's server-side OIDC path to Authentik. The monitoring VM was
resolving the identity hostname to the public edge, where its connection was
refused; the private NGINX route succeeds with the normal TLS hostname and
certificate. Preserve the browser's public authorization URL.

## Changes

- Manage a host-specific Authentik-to-private-edge mapping from generated
  `nginx_edge` topology.
- Verify provider discovery from the Grafana host and verify confidential
  client authentication using an intentionally invalid authorization code.
- Keep client secret material in ignored local secret storage and suppress it
  from Ansible output.

## Verification

- Role tests assert the host mapping, dynamic topology source, and no-log client
  authentication probe.
- Ansible syntax and focused role tests pass.
- Live checks currently pass: Grafana resolves Authentik through the private
  edge; HTTPS discovery returns 200; the configured confidential client returns
  `invalid_grant` for an intentionally invalid authorization code; Grafana's
  OAuth entry point returns 302; and its local and public login pages return
  200. The evidence records verification of the existing host-specific
  workaround, not a full managed-role converge.

## Safety and status

- No Authentik client secret is rotated and no OAuth provider is re-created.
- No public DNS, Authentik user, or access group is changed.
- No Tailscale ACL, split-DNS, or control-plane setting is changed.
- A normal converge remains unsafe: the repository's generated topology points
  at a different private network than the verified live fleet, and `make
  validate` currently fails on generated `platform.yml` drift. Reconcile the
  selected deployment topology before applying the role through the governed
  workflow; do not override the edge address ad hoc.
