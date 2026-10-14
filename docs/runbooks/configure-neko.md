# Configure and troubleshoot Neko

Neko is the platform's per-operator interactive browser runtime. The browser UI
is published at the deployment's `browser` subdomain and protected by the
shared NGINX Edge oauth2-proxy using the Authentik `ops-portal` OIDC provider.
The current Neko v2-compatible image still uses its built-in multi-user login
for the final browser-session bootstrap. That built-in password is not a secret
or an independent security boundary: only the Authentik edge gate and the
runtime-comms firewall may authorize access to a per-user instance. The role
assigns existing Authentik users to isolated Neko instances; it never provisions
an identity or changes a user's password.

## Safe configuration

- Keep the generic operator mapping in `inventory/group_vars/all/neko.yml`.
- Put additional operator mappings in the selected deployment's private sibling
  `neko.yml` overlay. Do not add real operator emails or instance names to the
  tracked generic inventory.
- The selected overlay is loaded by `platform/ansible/execution_scopes.py`; do
  not copy it into a worktree or another deployment's overlay.
- Do not remove all configured instances unless a complete Neko teardown is
  explicitly intended and `neko_allow_empty_instances: true` is set in that
  selected private overlay.
- Treat each instance's persistent `cache` and `config` directories as
  confidential browser state. They may contain visited-site data or
  authenticated cookies. The data catalog currently declares no finite
  retention or backup policy for them.

Validate the source and instance mapping before a live change:

```bash
uvx --from pyyaml python scripts/neko_tool.py validate
make syntax-check-neko
```

Apply the full runtime, Authentik assignment, and edge declaration through the
canonical playbook target:

```bash
make converge-neko env=production
```

If the runtime and Authentik assignments are already verified and only the
NGINX route needs reconciliation, select the isolated edge publication tag:

```bash
make converge-neko env=production EXTRA_ARGS='--tags neko-edge-publication'
```

## Verify the operator flow

1. Confirm the private Neko readiness endpoint returns HTTP 200 from the
   monitoring or runtime network.
2. In a clean browser session, request the public browser URL. An unauthenticated
   request must enter the Authentik OIDC flow; it must not render Neko directly.
3. Sign in as an assigned Authentik user and confirm that the generated email
   backend map reaches only that user's Neko instance.
4. Confirm an authenticated but unassigned user receives HTTP 403.
5. Verify WebSocket signalling and a WebRTC media session. Keep the configured
   media UDP range distinct per instance; never publish the Neko TCP listener
   directly to the public internet.

The TCP signalling listener must remain reachable only from the NGINX edge and
the private monitoring probe. Do not treat the Neko v2 login prompt, its
built-in password, or direct UDP media as an authentication control. A future
Neko image/auth-provider migration must replace the bootstrap behavior only
after the exact candidate has passed a fresh browser and WebRTC test.

The automated signalling SLO probes the private endpoint. It does not prove the
Authentik login, identity-to-instance mapping, or public WebRTC path; retain
those browser checks as separate end-to-end evidence.

## Diagnose an edge authentication failure

Check the Authentik provider discovery endpoint and the NGINX Edge oauth2-proxy
service independently. The oauth2-proxy issuer must be the generated Authentik
`ops-portal` provider URL, not a retired Keycloak issuer. On the edge host:

```bash
systemctl status <config-prefix>-ops-portal-oauth2-proxy.service --no-pager
systemctl show <config-prefix>-ops-portal-oauth2-proxy.service -p NRestarts -p ExecMainStatus
journalctl -u <config-prefix>-ops-portal-oauth2-proxy.service -n 100 --no-pager
nginx -t
```

Do not print the oauth2-proxy configuration or environment in incident output:
it contains the OIDC client secret and session cookie secret. Reconcile edge
identity configuration using `make configure-edge-publication env=production`
and validate through the deployment's governed secret overlay. A successful
NGINX syntax check alone is not proof that OIDC discovery or browser login works.
