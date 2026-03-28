# Configure Coolify

## Purpose

This runbook converges the dedicated `coolify-lv3` PaaS VM, publishes the protected dashboard at `https://coolify.lv3.org`, enables the private API path through the Proxmox host Tailscale proxy, and verifies repo-driven application deployment through the `*.apps.lv3.org` wildcard ingress lane.

## Managed Surfaces

- runtime role: `collections/ansible_collections/lv3/platform/roles/coolify_runtime`
- playbook: `playbooks/coolify.yml`
- live-apply wrapper: `playbooks/services/coolify.yml`
- dashboard hostname: `https://coolify.lv3.org`
- app hostname space: `https://apps.lv3.org`, `https://*.apps.lv3.org`
- controller-local artifacts: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/coolify/`

## Preconditions

- the focused repository validation slice passes:
  `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_coolify_tool.py tests/test_coolify_runtime_role.py tests/test_coolify_playbook.py tests/test_lv3_cli.py -q`
- `./scripts/validate_repo.sh agent-standards` passes
- the controller has the bootstrap SSH key configured for the Proxmox jump path
- `HETZNER_DNS_API_TOKEN` is available for dashboard DNS publication and shared edge certificate expansion
- the shared NGINX edge, Keycloak, and oauth2-proxy path are already converged

On a workstream branch, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` can remain blocked until the final merge-to-main step updates the protected canonical truth in `versions/stack.yaml`.

## Converge

```bash
HETZNER_DNS_API_TOKEN=... make converge-coolify
```

This workflow:

- provisions or updates the `coolify-lv3` guest on Proxmox
- converges Docker and the Coolify runtime stack on the guest
- bootstraps the initial Coolify root account, enables the API, and mints the durable API token
- registers the local deployment server inside Coolify using the repo-managed SSH key
- renders the host-side private TCP proxy and the public NGINX edge routes

## Verification

Private API whoami:

```bash
python3 scripts/coolify_tool.py whoami
```

Dashboard auth boundary:

```bash
curl -ksSI --resolve coolify.lv3.org:443:65.108.75.123 https://coolify.lv3.org/
```

Repo deployment:

```bash
python3 scripts/coolify_tool.py deploy-repo \
  --repo https://github.com/coollabsio/coolify-examples \
  --branch main \
  --base-directory /static \
  --app-name repo-smoke \
  --build-pack static \
  --subdomain repo-smoke \
  --wait \
  --timeout 900
```

App reachability:

```bash
curl -ksSI --resolve repo-smoke.apps.lv3.org:443:65.108.75.123 https://repo-smoke.apps.lv3.org/
```

Wildcard apex behavior without a default app:

```bash
curl -ksSI --resolve apps.lv3.org:443:65.108.75.123 https://apps.lv3.org/
```

Expected results:

- `coolify.lv3.org` returns `302` to the shared oauth2-proxy sign-in flow
- `repo-smoke.apps.lv3.org` returns `200`
- `apps.lv3.org` returns `404` until an apex app is assigned

If public DNS has not propagated to the controller yet, keep using `--resolve` against `65.108.75.123` for verification and record that separately from DNS visibility.

## Controller-Local Artifacts

- `.local/coolify/root-password.txt`
- `.local/coolify/api-token.txt`
- `.local/coolify/server-key`
- `.local/coolify/server-key.pub`
- `.local/coolify/deployments/`

These files are generated or refreshed by the repo-managed automation and are not committed.

## Access Model

- `coolify.lv3.org` is protected by the shared oauth2-proxy and Keycloak edge flow.
- the Coolify API is consumed from the controller through the Proxmox host Tailscale TCP proxy, not over the public edge
- `*.apps.lv3.org` is intentionally public because it is the published application ingress lane

## Rollback

- revert the repo change
- rerun `make converge-coolify`
- if the public app route must be withdrawn immediately, remove the Coolify edge entries and rerun `make configure-edge-publication`
