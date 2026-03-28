# Platform Operations Portal

## Purpose

The operations portal is a generated static site under `build/ops-portal/`.

It gives operators one place to answer:

- where does a service live
- which VM owns it
- what subdomain points at it
- which runbook documents it
- which ADR introduced it
- which agent tools already exist

## Generation

Generate the portal locally:

```bash
make generate-ops-portal
```

This renders:

- `build/ops-portal/index.html`
- `build/ops-portal/environments/index.html`
- `build/ops-portal/vms/index.html`
- `build/ops-portal/subdomains/index.html`
- `build/ops-portal/runbooks/index.html`
- `build/ops-portal/adrs/index.html`
- `build/ops-portal/agents/index.html`

The generator reads:

- `config/environment-topology.json`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/agent-tool-registry.json`
- `versions/stack.yaml`
- `docs/adr/*.md`
- `docs/runbooks/*.md`

## Health Data

The portal can embed a generation-time health snapshot:

```bash
uvx --from pyyaml python scripts/generate_ops_portal.py \
  --health-snapshot path/to/snapshot.json \
  --write
```

When no snapshot is provided, the portal still renders and marks service health as `unknown`.

## Validation

Run:

```bash
uvx --from pyyaml python scripts/generate_ops_portal.py --check
```

That renders the site in a temporary directory and verifies that all expected pages are present.

## Deployment Boundary

This workstream implements the generated site and repo automation.

The portal publication path now has two repo-managed components:

- `public_edge_oidc_auth` runs `oauth2-proxy` on `nginx-lv3` and uses the Keycloak client secret mirrored at `.local/keycloak/ops-portal-client-secret.txt`
- `nginx_edge_publication` serves `build/ops-portal/` and gates `ops.lv3.org` behind `/oauth2/*` instead of serving the static files anonymously

Internal verification should show an unauthenticated request redirecting to the sign-in flow:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes ops@100.118.189.95 \
  'curl -k -I -H "Host: ops.lv3.org" https://10.10.10.10'
```

Expected result: `HTTP/2 302` with `Location: https://ops.lv3.org/oauth2/sign_in?...`

External publication is now verified end to end:

- `https://ops.lv3.org` returns `302` to `/oauth2/sign_in` for unauthenticated requests
- `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration` returns `200`

Two network details are now part of the live publication contract:

- `nginx-lv3` sets `proxmox_firewall_enabled: false`, which leaves `net0` at `firewall=0` and avoids the Proxmox `fwbr*` bridge path that was dropping public `80/443` SYNs before the guest kernel saw them
- `docker-runtime-lv3` must allow TCP `8091` from `nginx-lv3` in both the Proxmox VM firewall and the in-guest nftables policy so `sso.lv3.org` and `oauth2-proxy` can reach Keycloak

If cloud access to `https://ops.lv3.org` regresses, verify those two conditions before changing the portal or Keycloak configuration again.

## Structured Runbook Launcher

The interactive portal runbook panel now loads its entries from the platform API gateway instead of maintaining a separate local workflow-only list.

Operator flow:

1. Open `https://ops.lv3.org`.
2. Use the **Runbook Launcher** panel.
3. Pick one runbook that explicitly opts into the `ops_portal` delivery surface.
4. Submit JSON parameters if the runbook requires them.

The safest verification path is the repo-managed `docs/runbooks/validation-gate-status.yaml` runbook, which is read-only and returns the current validation-gate summary through the shared runbook service.

Portal operators do not need to know how the workflow is wired underneath:

- the portal parses JSON parameters and forwards them as a thin adapter
- the API gateway enforces auth and resolves the shared runbook contract
- the shared use-case service owns runbook lookup, surface allowlists, templating, workflow sequencing, and persisted run records

## Declared-To-Live Attestation

The interactive portal overview now includes the declared-to-live attestation rollup from the platform API gateway.

Operator flow:

1. Open `https://ops.lv3.org`.
2. Check the **Attested** summary tile in the overview strip.
3. Open a service card and read the `Declared-live ...` hint strip for endpoint, route, and receipt witness state.
4. If the overview banner says declared-to-live data is degraded, verify the upstream gateway payload before changing portal code.

Internal verification from a trusted network path:

```bash
curl -sf http://10.10.10.20:8092/partials/overview | rg 'Attested|Declared-live'
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/attestation
```

Expected result:

- the portal overview shows the attestation summary tile
- affected service cards render `Declared-live <status> · endpoint <status> / route <status> / receipt <status>`
- the gateway route returns the same witness record shape the portal is rendering
