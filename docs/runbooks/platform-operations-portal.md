# Platform Operations Portal

## Purpose

The operations portal is a repo-managed interactive runtime served at
`https://ops.lv3.org` from `docker-runtime-lv3`.

It gives operators one place to answer:

- where does a service live
- which VM owns it
- what subdomain points at it
- which runbook documents it
- which ADR introduced it
- which agent tools already exist
- which first-party surface should I jump to next

The current portal combines:

- a FastAPI-based operator shell under `scripts/ops_portal/`
- repo-synced catalogs and receipts mirrored into `/opt/ops-portal/data`
- dashboard actions such as the runbook launcher
- a shared masthead application launcher with purpose grouping, persona filters,
  favorites, and recent destinations

## Local Generation

Generate the static snapshot locally when you need a read-only render for checks,
design review, or fallback artifacts:

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

The generated snapshot is not the production runtime. Production serves the
interactive app from `scripts/ops_portal/` and syncs the same catalogs into the
container data directory during converge.

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
make syntax-check-ops-portal
```

That covers both sides of the portal contract:

- `generate_ops_portal.py --check` verifies the static snapshot still renders
- `make syntax-check-ops-portal` verifies the interactive runtime playbook and
  role wiring

For the launcher-specific runtime behavior, also run the focused tests:

```bash
uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal.py -q
```

## Deployment

For a repo-managed converge without the production live-apply guard:

```bash
make converge-ops-portal env=production
```

For the governed production replay used during live applies:

```bash
make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true'
```

`bypass_promotion=true` is the documented break-glass path for direct production
replays from a workstream branch. The Make target still enforces canonical truth,
interface contracts, redundancy checks, immutable-guest checks, and emits the
promotion-bypass audit event before running the service playbook.

## Publication Boundary

The portal publication path has three repo-managed components:

- `ops_portal_runtime` serves the interactive FastAPI shell on
  `docker-runtime-lv3`
- `public_edge_oidc_auth` runs `oauth2-proxy` on `nginx-lv3` and uses the Keycloak client secret mirrored at `.local/keycloak/ops-portal-client-secret.txt`
- `nginx_edge_publication` forwards authenticated traffic for `ops.lv3.org` to
  the interactive runtime instead of serving the old static snapshot directly

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

## Application Launcher

ADR 0235 adds a shared masthead application launcher as the default
cross-application switcher inside the interactive portal.

Launcher inputs come from repo-managed data:

- `config/service-capability-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/workflow-catalog.json`
- `config/persona-catalog.json`

Workflow entries only appear when the workflow declares
`human_navigation.launcher` metadata in the workflow catalog.

Operator flow:

1. Open `https://ops.lv3.org` and complete the normal sign-in flow.
2. Select **Application Launcher** in the masthead.
3. Search for a destination, switch persona if needed, and use the purpose
   groups to narrow the list.
4. Toggle the star button on any destination to add or remove it from
   favorites.
5. Open a destination through the launcher to record it in recent destinations.

Expected behavior:

- the launcher groups entries into `Operate`, `Observe`, `Learn`, `Plan`, and
  `Administer`
- switching persona changes which destinations stay visible without mutating the
  underlying catalogs
- favorites and recent destinations persist for the current browser session
- launcher redirects preserve the destination URL while recording the recent
  visit server-side through the portal session

The safest live verification path is:

1. favorite `Keycloak` or another common admin surface
2. open `Validation Gate Status` or `Drift Status` from the launcher
3. reopen the launcher and confirm the destination now appears under
   **Recent destinations**

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
