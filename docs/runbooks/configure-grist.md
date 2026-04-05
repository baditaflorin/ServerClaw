# Configure Grist

This runbook covers the repo-managed Grist deployment introduced by [ADR 0279](../adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md).

## Scope

The Grist workflow converges:

- the Grist runtime and persistent document store on `docker-runtime-lv3`
- the public hostname `grist.lv3.org` on the shared NGINX edge
- the dedicated Keycloak OIDC client used by the Grist sign-in flow
- the controller-local Grist session secret mirrored under `.local/grist/`

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.lv3.org`
- the Keycloak discovery document answers at `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
- Hetzner DNS API credentials are available when the edge certificate needs expansion

The Grist role now waits for that discovery document through the shared edge
route before startup and, if the local auth surface still returns
`"errMessage":"No login system is configured"`, it force-recreates only the
`grist` container after rechecking discovery. Treat that automated recovery as
part of the normal convergence path rather than as an exceptional manual fix.

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... make live-apply-service service=grist env=production
```

This is the required path for the authoritative platform-version bump because
`make live-apply-service` updates the canonical truth surfaces after the
merged-main replay.

On a non-`main` workstream branch, expect that target to stop at the canonical
truth gate if protected shared integration files such as `README.md` would need
refreshing. That stop is expected branch-local behavior; use the direct scoped
runner below and record the evidence in the workstream receipt instead of
editing protected release truth on the branch.

On a workstream branch where protected integration files must remain untouched, run the service playbook directly:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local \
ANSIBLE_REMOTE_TEMP=/tmp \
./scripts/run_with_namespace.sh uvx --from pyyaml python \
  ./scripts/ansible_scope_runner.py run \
  --inventory ./inventory/hosts.yml \
  --playbook ./playbooks/services/grist.yml \
  --env production \
  -- \
  --private-key ./.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/grist/`:

- `session-secret.txt`

The Keycloak client secret is mirrored under `.local/keycloak/grist-client-secret.txt`.

## Runtime layout

The runtime stores persistent Grist state under `/opt/grist/persist` on
`docker-runtime-lv3`:

- `/opt/grist/persist/docs`
- `/opt/grist/persist/home.sqlite3`

These files are the authoritative Grist document and instance store and must
stay within the documented backup scope.

The live March 31 replay also confirmed that `/opt/grist/persist` and its
contents must remain owned by runtime UID/GID `1001:1001`; if a manual repair
ever resets that ownership, rerun the role before trusting Grist login or
document persistence again.

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service grist
uv run --with pytest --with jsonschema --with pyyaml python -m pytest -q tests/test_grist_runtime_role.py tests/test_grist_playbook.py tests/test_keycloak_runtime_role.py tests/test_openbao_compose_env_helper.py tests/test_ansible_execution_scopes.py tests/test_validate_service_completeness.py tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_container_image_policy.py
uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0279syntax --playbook playbooks/services/grist.yml --env production -- --private-key .local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check
./scripts/validate_repo.sh agent-standards workstream-surfaces data-models
make preflight WORKFLOW=live-apply-service service=grist env=production
uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:grist
uv run --with pyyaml python scripts/standby_capacity.py --service grist
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service grist
uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grist --allow-in-place-mutation
```

Runtime verification:

```bash
curl -fsS https://grist.lv3.org/status
curl -sS -D /tmp/grist-o-docs.headers https://grist.lv3.org/o/docs/ -o /dev/null
sed -n '1,20p' /tmp/grist-o-docs.headers
rg '^location: https://sso.lv3.org/realms/lv3/protocol/openid-connect/auth' /tmp/grist-o-docs.headers
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand='ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  "sudo docker logs --tail 200 grist 2>&1 | egrep 'OIDCConfig|loginMiddlewareComment' | tail -n 20"
python3 - <<'PY'
import urllib.request
with urllib.request.urlopen("https://grist.lv3.org/status", timeout=10) as resp:
    print(resp.status, resp.read().decode("utf-8", "replace").strip())
PY
```

The public `/status` endpoint should return `200` and the body
`Grist server(home,docs,static) is alive.` while unauthenticated requests to
`https://grist.lv3.org/o/docs/` should return `HTTP 302` into the Keycloak
OIDC flow at `https://sso.lv3.org/realms/lv3/protocol/openid-connect/auth...`.
The container logs should include `OIDCConfig: initialized with issuer
https://sso.lv3.org/realms/lv3` and `loginMiddlewareComment: oidc`.

## Operating notes

- Grist uses the named Keycloak operator email as the repo-managed first-admin path.
- Do not store platform-authoritative host, network, or release truth only inside Grist; continue to keep canonical platform state in repo-managed files and governed systems such as NetBox or PostgreSQL.
- Treat `.local/grist/` and `.local/keycloak/grist-client-secret.txt` as sensitive controller-only material.
- Keep `grist.lv3.org/status` publicly reachable through the shared edge for health verification.
- Document routes require authentication for the org workspace; individual documents that the owner marks as public are reachable without login via the share link.
- If the first publication run fails before Hetzner DNS state is observable, confirm `grist.lv3.org` resolves to `65.108.75.123` and rerun the scoped playbook; the DNS and edge publication path is idempotent once the record exists.
- If Grist ever serves the blocked auth page with `No login system is configured`, rerun the repo-managed play first. The current role is expected to recover that startup race automatically by rechecking Keycloak discovery and force-recreating only the Grist container.
- When adding a new user to the `lv3` org, the recommended path is through the Grist UI (Admin panel → Users). Direct SQLite edits to `home.sqlite3` are a break-glass measure only and must be followed by a managed live-apply to restore idempotent state.
- Always use `docker compose up -d --force-recreate` to apply env file changes. `docker compose restart` reuses the cached container environment and will not pick up changes made to `grist.env`.

## Postmortem: 2026-04-05 Grist SSO incident

### Timeline

| UTC | Event |
|-----|-------|
| ~11:30 | Grist at `grist.lv3.org` returns "Something went wrong / There was an unknown error" |
| ~11:45 | Root cause identified: `grist.env` was correct but the container had been running for 19+ hours without picking up OIDC env. Container restart resolved `No login system is configured` |
| ~12:00 | Second issue: user `busui.matei1994@gmail.com` receives "Access denied". Fix: direct SQLite `INSERT INTO group_users` to add user to the `lv3` org editors group |
| ~12:15 | Third issue: JS error `Cannot figure out what organization the URL is for`. Added `GRIST_SERVE_SAME_ORIGIN=true` to template and env. Error persists |
| ~12:30 | Root cause isolated: NGINX CSP header `script-src 'self'` blocks Grist's inline `<script>window.gristConfig = {...}</script>`. Without gristConfig, client-side URL→org resolution fails before login even starts |
| ~12:45 | Added `grist.lv3.org` CSP override to `nginx_edge_publication/defaults/main.yml` with `script-src 'self' 'unsafe-inline'` |
| ~13:00 | Discovered `nginx_edge_publication` preliminary render fails with `public_edge_site_tls_materials is undefined`. Added `{}` default to role defaults |
| ~13:10 | Discovered `public-edge.yml` playbook fails on missing `build/changelog-portal/` dir (worktree has no built portal). Bypassed with `-e public_edge_sync_generated_static_dirs=false` |
| ~13:15 | Public-edge playbook succeeds (ok=87 changed=4). Grist loads and SSO login works |
| ~13:30 | Separate request: public shared documents blocked by `GRIST_FORCE_LOGIN=true`. Set to `false` with `GRIST_ANONYMOUS_PLAYGROUND=false`. Applied via `docker compose up -d --force-recreate` |

### Root causes

1. **Grist's inline bootstrap script blocked by default NGINX CSP.** The platform default `script-src 'self'` is correct for most services but incompatible with Grist's architecture. Grist injects org and config metadata as an inline script on every HTML response. A per-service CSP override for `grist.lv3.org` was missing from `nginx_edge_publication/defaults/main.yml`.

2. **`GRIST_FORCE_LOGIN=true` default too restrictive for public document sharing.** Setting force-login blocks even documents that the document owner has explicitly granted public access to. The correct posture is `GRIST_FORCE_LOGIN=false` + `GRIST_ANONYMOUS_PLAYGROUND=false`: public doc links work, but the org workspace and doc creation remain authenticated.

3. **Missing `public_edge_site_tls_materials` default caused preliminary render failure.** The `nginx_edge_publication` role runs a preliminary NGINX config render before Let's Encrypt certificate issuance, then a final render after TLS materials are collected. The template referenced `public_edge_site_tls_materials` without a default, making the preliminary render always fail on a first run or after a cert refresh.

4. **`docker compose restart` does not re-read env files.** The stale OIDC config in the long-running container was not a config drift issue — the file was correct — but the container had not been recreated since before the env was written. This delayed diagnosis by hiding the true state.

### Fixes applied

| File | Change |
|------|--------|
| `roles/nginx_edge_publication/defaults/main.yml` | Added `grist.lv3.org` CSP override: `script-src 'self' 'unsafe-inline'`, `connect-src` includes `https://sso.lv3.org` |
| `roles/nginx_edge_publication/defaults/main.yml` | Added `public_edge_site_tls_materials: {}` default |
| `roles/grist_runtime/templates/grist.env.j2` | Added `GRIST_SERVE_SAME_ORIGIN=true`, `GRIST_ANONYMOUS_PLAYGROUND` |
| `roles/grist_runtime/defaults/main.yml` | Changed `grist_force_login: true` → `false`; added `grist_anonymous_playground: false` |

### Action items

- [ ] Run `make live-apply-service service=grist` from `main` once the branch merges to encode all changes in the canonical truth surface
- [ ] Run `make live-apply-service service=public-edge` from `main` to push the CSP override and TLS default through the governed path
- [ ] Add CSP validation for `'unsafe-inline'` requirement to the Grist role tests
- [ ] Document the `--force-recreate` requirement in the ansible role's `argument_specs.yml` usage notes
