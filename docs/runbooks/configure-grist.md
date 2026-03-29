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
- Hetzner DNS API credentials are available when the edge certificate needs expansion

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
curl -sSI https://grist.lv3.org/o/docs/
python3 - <<'PY'
import urllib.request
with urllib.request.urlopen("https://grist.lv3.org/status", timeout=10) as resp:
    print(resp.status, resp.read().decode("utf-8", "replace").strip())
PY
```

The public `/status` endpoint should return `200` and the body
`Grist server(home,docs,static) is alive.` while unauthenticated requests to
`https://grist.lv3.org/o/docs/` should still redirect into the login-controlled
surface.

## Operating notes

- Grist uses the named Keycloak operator email as the repo-managed first-admin path.
- Do not store platform-authoritative host, network, or release truth only inside Grist; continue to keep canonical platform state in repo-managed files and governed systems such as NetBox or PostgreSQL.
- Treat `.local/grist/` and `.local/keycloak/grist-client-secret.txt` as sensitive controller-only material.
- Keep `grist.lv3.org/status` publicly reachable through the shared edge for health verification, but treat document routes as authenticated operator surfaces.
- If the first publication run fails before Hetzner DNS state is observable, confirm `grist.lv3.org` resolves to `65.108.75.123` and rerun the scoped playbook; the DNS and edge publication path is idempotent once the record exists.
