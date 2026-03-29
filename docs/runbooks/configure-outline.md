# Configure Outline

This runbook covers the repo-managed Outline deployment introduced by [ADR 0199](../adr/0199-outline-living-knowledge-wiki.md).

## Scope

The Outline workflow converges:

- the PostgreSQL backend on `postgres-lv3`
- the Outline runtime, Redis cache, and MinIO attachment store on `docker-runtime-lv3`
- the public hostname `wiki.lv3.org` on the shared NGINX edge
- the dedicated Keycloak OIDC client used by the Outline sign-in flow
- the shared logout handoff from Outline to Keycloak and then to the shared `oauth2-proxy` cookie-cleanup endpoint on `ops.lv3.org`
- the controller-local Outline API token and the initial living knowledge collections

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.lv3.org`
- the automation password file exists at `.local/keycloak/outline.automation-password.txt`
- Hetzner DNS API credentials are available when the edge certificate needs expansion

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... make live-apply-service service=outline env=production
```

This is the required path for the authoritative platform-version bump because `make live-apply-service` updates the canonical truth surfaces after the merged-main replay.

On a workstream branch where protected integration files must remain untouched, run the service playbook directly:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local \
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

The Keycloak client secret is mirrored under `.local/keycloak/outline-client-secret.txt`.

## Manual-free bootstrap path

The role performs the first Outline admin bootstrap without browser interaction by:

1. following the normal `wiki.lv3.org -> Keycloak -> wiki.lv3.org` OIDC browser flow with the repo-managed `outline.automation` account
2. extracting the resulting Outline app token
3. minting the long-lived Outline API token stored under `.local/outline/api-token.txt`
4. pruning the default `Welcome` collection after bootstrap
5. syncing the living collection landing pages and indexes while deleting duplicate managed landing docs if they drift in

Outline logout remains app-local first, but the repo-managed `OIDC_LOGOUT_URI` now hands the browser to Keycloak with a declared post-logout return path through `https://ops.lv3.org/.well-known/lv3/session/proxy-logout` so shared edge cookies are cleared before the final logged-out landing page.

## Syncing knowledge surfaces

To refresh the living knowledge docs on demand:

```bash
python3 scripts/sync_docs_to_outline.py sync --base-url https://wiki.lv3.org
```

To verify the managed collections and landing pages:

```bash
python3 scripts/sync_docs_to_outline.py verify --base-url https://wiki.lv3.org
```

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service outline
uv run --with pytest python -m pytest tests/test_outline_runtime_role.py tests/test_outline_playbook.py tests/test_outline_sync.py tests/test_keycloak_runtime_role.py tests/test_release_manager.py tests/test_generate_platform_vars.py
uv run --with pyyaml --with jsonschema python -m unittest tests.test_grafana_sso_role tests.test_session_logout_verify
./scripts/validate_repo.sh agent-standards
./scripts/validate_repo.sh generated-portals
uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:outline
uv run --with pyyaml python scripts/standby_capacity.py --service outline
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service outline
```

Runtime verification:

```bash
curl -fsS https://wiki.lv3.org/_health
python3 scripts/sync_docs_to_outline.py verify --base-url https://wiki.lv3.org
```

The verify command asserts that the required collections exist and that the repo-managed landing docs were published successfully. A successful sync keeps the top-level collection set at `ADRs`, `Runbooks`, `Incident Postmortems`, `Agent Findings`, and `Architecture`.

## Mainline replay notes

- The authenticated Keycloak admin API is warmed immediately after restart so the first realm-management query does not race the container startup path.
- The merged-main replay may retry the public `https://wiki.lv3.org/_health` probe briefly after the edge certificate expands to include `wiki.lv3.org`; a short retry window is expected during the NGINX reload.
