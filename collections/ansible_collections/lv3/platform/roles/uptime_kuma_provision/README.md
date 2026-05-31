# uptime_kuma_provision

Generic, registry-driven provisioning of Uptime Kuma **monitors** and the
public **status page**. This role configures a *running* Uptime Kuma instance;
the container itself is deployed by `uptime_kuma_runtime`.

## Why this exists

Deploying the Uptime Kuma container leaves it empty — no monitors, no status
page, no admin account. The previous workflow required a manual
`make uptime-kuma-manage ACTION=…` ritual run from the controller, which only
works if the operator's machine can reach the instance (the public edge is
behind oauth2-proxy/SSO, which blocks the socket.io API).

This role makes provisioning a first-class, idempotent part of the converge.

## How it is generic

Nothing about the deployment is hardcoded:

| Concern            | Source |
|--------------------|--------|
| API base URL       | `http://127.0.0.1:{{ internal_port }}` — port from `platform_service_registry`. The agent runs **on the VM**, so no IP and no SSH tunnel are needed. |
| Which services     | Every service in `config/health-probe-catalog.json` with `uptime_kuma.enabled == true` becomes a monitor. Add a service to the catalog → it appears automatically. |
| Monitor URLs       | The catalog's `example.com` / `lv3` placeholders are substituted with `platform_domain` and the Keycloak realm at runtime. |
| Status page        | Auto-built: a single "Platform Services" group covering every monitor, titled and domained from `platform_domain` (`status.<domain>`). |

## What it does (idempotent)

1. Derives the internal port from the service registry.
2. Installs a minimal venv (`requests`, `python-socketio`) on the VM.
3. Copies a **self-contained** agent (`files/uptime_kuma_agent.py`) and the
   health-probe catalog to the VM.
4. Seeds the VM with any existing controller-side admin session so the stored
   token is reused.
5. Runs the agent's `provision` command: bootstrap the admin (first run only),
   reconcile monitors, reconcile the status page.
6. Fetches the admin session back to `.local/uptime-kuma/admin-session.json`.

## Key variables

See `defaults/main.yml`. Most are registry/identity-derived. The one you may
need to override:

- `uptime_kuma_provision_keycloak_realm` — defaults to `keycloak_realm_name`
  (the domain's first label). If the **live** realm name differs (e.g. the
  domain is `0mcp.com` but the realm is still named `0mpc`), override it:

  ```
  -e uptime_kuma_provision_keycloak_realm=0mpc
  ```

## Running it

It runs automatically as the final play of `playbooks/uptime-kuma.yml`
(`make deploy-uptime-kuma env=production`). To run only the provisioning step:

```
make provision-uptime-kuma env=production
```
