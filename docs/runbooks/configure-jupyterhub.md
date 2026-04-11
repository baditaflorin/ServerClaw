# Configure JupyterHub

This runbook covers the repo-managed JupyterHub deployment introduced by
[ADR 0291](../adr/0291-jupyterhub-as-the-interactive-notebook-environment.md).

## Scope

The JupyterHub workflow converges:

- the public hostname `notebooks.example.com` on the shared NGINX edge
- the JupyterHub hub runtime on `docker-runtime`
- the dedicated Keycloak OIDC client used by the browser login flow
- the DockerSpawner-backed single-user notebook contract
- the service-local `jupyterhub-shared` MinIO bucket used for shared notebook
  assets
- the OpenBao-backed runtime secret injection used for the hub and spawned user
  notebook environments

## Current Live Contract

The current live implementation makes these exploratory data and model surfaces
available inside spawned notebook servers:

- Ollama through `OPENAI_BASE_URL` and `OLLAMA_BASE_URL`, routed from the
  notebook container to the runtime host through `host.docker.internal`
- the private platform-context API through `PLATFORM_CONTEXT_URL`, also routed
  from the notebook container through `host.docker.internal`
- the service-local MinIO bucket `jupyterhub-shared`
- the repo-managed Python analysis libraries baked into the single-user image

This is the current safe live contract. It deliberately does not claim that the
future shared global MinIO, raw Qdrant, or LiteLLM contracts are already live.

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload already exists under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.example.com`
- Hetzner DNS API credentials are available when the edge certificate or DNS
  records need expansion

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... make live-apply-service service=jupyterhub env=production
```

This is the authoritative exact-main replay path because `make live-apply-service`
is what updates the canonical release and platform truth surfaces.

On a non-`main` workstream branch where protected release files must remain
untouched, prefer the service-scoped converge target:

```bash
HETZNER_DNS_API_TOKEN=... make converge-jupyterhub env=production
```

That entrypoint keeps the protected release files untouched and now repairs the
shared edge-generated portal artifacts during `make preflight` so a fresh
worktree does not fail later inside `nginx_edge_publication`.

If you need to run the playbook directly instead of the make target:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox-host_server-ansible-local \
ANSIBLE_REMOTE_TEMP=/tmp \
./scripts/run_with_namespace.sh uvx --from pyyaml python \
  ./scripts/ansible_scope_runner.py run \
  --inventory ./inventory/hosts.yml \
  --playbook ./playbooks/services/jupyterhub.yml \
  --env production \
  -- \
  --private-key ./.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Before the direct playbook path, run either `make preflight
WORKFLOW=live-apply-service` or `make generate-edge-static-sites` so
`build/changelog-portal/` and `build/docs-portal/` exist for the shared edge
publication role.

## Generated Local Artifacts

The workflow maintains controller-local artifacts under `.local/jupyterhub/`:

- `service-api-token.txt`
- `minio-root-password.txt`

The Keycloak client secret is mirrored under
`.local/keycloak/jupyterhub-client-secret.txt`.

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service jupyterhub
uv run --with pytest python -m pytest tests/test_jupyterhub_runtime_role.py tests/test_jupyterhub_playbook.py tests/test_keycloak_runtime_role.py
uv run --with pyyaml python scripts/generate_platform_vars.py --check
uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py validate
./scripts/validate_repo.sh agent-standards health-probes
```

Runtime verification:

```bash
curl -fsS https://notebooks.example.com/hub/health
curl -I https://notebooks.example.com/hub/oauth_login
```

The role-level verification also exercises a repo-managed smoke user through the
local JupyterHub admin API, starts a single-user notebook server, checks the
spawned environment contract, confirms the `host.docker.internal` gateway
mapping inside the notebook container, and checks the shared MinIO, Ollama, and
platform-context health paths from inside the notebook container.

## Operational Notes

- JupyterHub is an exploratory environment. Promote validated notebook logic
  into repo-managed workflows rather than treating live notebooks as production
  automation.
- Per-user notebook files persist on Docker named volumes. Shared notebook
  assets that need collaborative handoff should be copied into the
  `jupyterhub-shared` MinIO bucket from inside the notebook environment.
- The public browser login flow is upstream-authenticated by JupyterHub itself
  through Keycloak OIDC; the shared edge does not layer `oauth2-proxy` in front
  of this hostname.
