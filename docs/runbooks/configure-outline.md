# Configure Outline

This runbook covers the repo-managed Outline deployment introduced by [ADR 0199](../adr/0199-outline-living-knowledge-wiki.md).

## Scope

The Outline workflow converges:

- the PostgreSQL backend on `postgres`
- the Outline runtime, Redis cache, and MinIO attachment store on `docker-runtime`
- the public hostname `wiki.example.com` on the shared NGINX edge
- the dedicated Authentik OIDC provider/application used by the selected Outline sign-in flow
- the Outline-to-Authentik logout handoff
- the controller-local Outline API token and the initial living knowledge collections

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Authentik is already deployed and healthy on `id.example.com`
- `.local/outline/api-token.txt` is present as a regular owner-only `0600` file
- Hetzner DNS API credentials are available when the edge certificate needs expansion

## Converge

On `main`, reconcile the Authentik provider/application first, then apply Outline:

```bash
HETZNER_DNS_API_TOKEN=... make converge-authentik env=production
HETZNER_DNS_API_TOKEN=... make live-apply-service service=outline env=production
```

This is the required path for the authoritative platform-version bump because `make live-apply-service` updates the canonical truth surfaces after the merged-main replay.

On a non-`main` workstream branch, expect that target to stop at the canonical
truth gate if protected shared integration files such as `README.md` would need
refreshing. That stop is expected branch-local behavior; use the direct scoped
runner below and record the evidence in the workstream receipt instead of
editing protected release truth on the branch.

On a workstream branch where protected integration files must remain untouched, run the service playbook directly:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox-host_server-ansible-local \
ANSIBLE_REMOTE_TEMP=/tmp \
./scripts/run_with_namespace.sh uvx --from pyyaml python \
  ./scripts/ansible_scope_runner.py run \
  --inventory ./inventory/hosts.yml \
  --playbook ./playbooks/services/outline.yml \
  --env production \
  -- \
  --private-key ./.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/outline/`:

- `database-password.txt`
- `secret-key.txt`
- `utils-secret.txt`
- `redis-password.txt`
- `minio-root-password.txt`
- `api-token.txt`

Every file in this directory is controller-local secret material. In
particular, `api-token.txt` must be a regular owner-only `0600` file. The
Outline publication gate refuses a symlink, non-regular file, empty file, or
broader mode.

The selected Authentik client secret is mirrored under
`.local/authentik/outline-client-secret.txt`.

## Durable API authority

Create the durable API token from an existing Authentik-authorized Outline
session, then store it only at `.local/outline/api-token.txt` with mode `0600`.
The token needs the scopes declared by `outline_api_token_scopes` in the role
defaults. The role intentionally does not automate a browser password flow or
write a token directly into the database.

If the token is lost, sign in through Authentik again with an authorized
operator, create a replacement scoped token in Outline, store it at that path,
and rerun the converge. Do not create an unmanaged identity or write a token
directly into the database.

Outline logout remains app-local first, then `OIDC_LOGOUT_URI` hands the
browser to Authentik's provider-scoped end-session flow. Authentik displays a
confirmation card for the completed Outline logout. Its central SSO session
remains active, so reopening Outline may silently sign the user back in. Use
the separate Authentik account-menu logout action when the user wants to end
the identity-provider session and sign out of all consumers.

The Outline runtime must start all four managed services: `web`, `worker`,
`websockets`, and `collaboration`. In particular, omitting `websockets` leaves
the HTTP UI functional but causes `/realtime` upgrades to fail at the public
edge. Keep the service list in both the static and OpenBao-rendered environment
templates in sync.

Verify login, the authenticated `/api/auth.info` session, the authenticated
Engine.IO `/realtime` WebSocket handshake, app-local logout, and SSO re-entry
with the repeatable clean-browser check:

```bash
uv run --no-project --with playwright python scripts/outline_authentik_e2e.py \
  --base-url "https://wiki.${PLATFORM_DOMAIN}" \
  --username gitea-e2e \
  --password-file "${LOCAL_ROOT}/authentik/gitea-e2e-initial-password.txt"
```

The logout assertion checks that Outline's own session is invalidated. It does
not require another Authentik password prompt, because provider-scoped logout
does not end the central SSO session.

## Syncing knowledge surfaces

To refresh the living knowledge docs on demand:

```bash
python3 scripts/sync_docs_to_outline.py sync --base-url https://wiki.example.com
```

To verify the managed collections and landing pages:

```bash
python3 scripts/sync_docs_to_outline.py verify --base-url https://wiki.example.com
```

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service outline
uv run --with pytest python -m pytest tests/test_outline_runtime_role.py tests/test_outline_playbook.py tests/test_outline_sync.py tests/test_authentik_oauth_reconcile.py tests/test_authentik_runtime_role.py tests/test_generate_cross_cutting_artifacts.py tests/test_generate_platform_vars.py
make preflight-outline-deployment-selection env=production
make syntax-check-outline
uv run --with pyyaml --with jsonschema python -m unittest tests.test_grafana_sso_role tests.test_session_logout_verify
./scripts/validate_repo.sh agent-standards
./scripts/validate_repo.sh generated-portals
uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:outline
uv run --with pyyaml python scripts/standby_capacity.py --service outline
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service outline
```

Runtime verification:

```bash
curl -fsS https://wiki.example.com/_health
curl -fsS https://id.example.com/application/o/outline/.well-known/openid-configuration
curl -fsSI https://wiki.example.com/auth/oidc
python3 scripts/sync_docs_to_outline.py verify --base-url https://wiki.example.com
```

The redirect must select `https://id.example.com/application/o/authorize/` and
client ID `outline`. The verify command asserts that all required collections
and repo-managed landing documents exist. Finish with the clean-browser E2E
command above. It exercises the Authentik callback, authenticated app session,
realtime upgrade, logout session clearing, and SSO re-entry in one browser
context.

## Mainline replay notes

- The merged-main replay may retry the public `https://wiki.example.com/_health` probe briefly after the edge certificate expands to include `wiki.example.com`; a short retry window is expected during the NGINX reload.
