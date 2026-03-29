# Configure Coolify

## Purpose

This runbook converges the dedicated `coolify-lv3` PaaS VM, publishes the protected dashboard at `https://coolify.lv3.org`, enables the private API path through the Proxmox host Tailscale proxy, and verifies both public and private repo-driven application deployment through the `*.apps.lv3.org` wildcard ingress lane.

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
- for private GitHub repository deployment bootstrap, `gh auth status` succeeds on
  the controller with repository administration access to the target repo

On a workstream branch, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` can remain blocked until the final merge-to-main step updates the protected canonical truth in `versions/stack.yaml`.

## Converge

```bash
HETZNER_DNS_API_TOKEN=... make converge-coolify
```

This workflow:

- provisions or updates the `coolify-lv3` guest on Proxmox
- publishes the managed `apps.lv3.org` and `*.apps.lv3.org` Hetzner DNS A records
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

Private GitHub Docker Compose deployment:

```bash
python3 scripts/coolify_tool.py deploy-repo \
  --repo git@github.com:baditaflorin/education_wemeshup.git \
  --branch main \
  --source private-deploy-key \
  --app-name education-wemeshup \
  --project "LV3 Apps" \
  --environment production \
  --build-pack dockercompose \
  --docker-compose-location /compose.yaml \
  --compose-domain catalog-web=education-wemeshup.apps.lv3.org \
  --ports 80 \
  --wait \
  --timeout 1800
```

Equivalent operator CLI dry run:

```bash
python3 scripts/lv3_cli.py deploy-repo \
  --repo git@github.com:baditaflorin/education_wemeshup.git \
  --source private-deploy-key \
  --app-name education-wemeshup \
  --build-pack dockercompose \
  --docker-compose-location /compose.yaml \
  --compose-domain catalog-web=education-wemeshup.apps.lv3.org \
  --wait \
  --dry-run
```

Named profile deployment for the current production education app:

```bash
make deploy-repo-profile PROFILE=education-wemeshup-production DEPLOY_PROFILE_ARGS='--wait'
```

Equivalent named-profile CLI:

```bash
python3 scripts/lv3_cli.py deploy-repo-profile education-wemeshup-production --wait
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
- public app hostnames under `*.apps.lv3.org` resolve through Hetzner DNS without manual per-app record creation
- the private GitHub wrapper run creates or reuses a local SSH keypair, a GitHub
  repo deploy key, and a Coolify private key before triggering the deployment
- the governed deploy wrapper cancels stale queued or in-progress deployments
  for the same application before it starts the next fresh rollout
- the governed deploy wrapper retries transient Docker registry and Alpine
  package-mirror failures up to three total attempts by default while preserving
  one command entry point for the operator
- the `coolify-lv3` Docker daemon now pins explicit public resolvers plus the
  approved Docker Hub mirror `https://mirror.gcr.io` so fresh repo deployments
  do not depend on the guest resolver state or anonymous origin pulls alone
- the approved repo-deploy base-image set now renders into
  `/opt/repo-deploy-image-cache/seed-plan.json`, refreshes through
  `lv3-repo-deploy-image-cache.timer`, and records its latest warm receipt at
  `/opt/repo-deploy-image-cache/warm-status.json`
- Docker Compose applications must use `--compose-domain SERVICE=DOMAIN`
  instead of the top-level `--domain` or `--subdomain` flags
- the wildcard `*.apps.lv3.org` edge must proxy to the Coolify VM over
  `https://<coolify-vm>:443`; proxying to plain HTTP causes an infinite `307`
  loop for healthy apps
- the `coolify-lv3` guest firewall must allow `nginx-lv3` to reach TCP `443`,
  not just `80` and `8000`, or the public edge will time out while connecting
  upstream
- `apps.lv3.org` returns `404` until an apex app is assigned

If public DNS has not propagated to the controller yet, keep using `--resolve` against `65.108.75.123` for verification and record that separately from DNS visibility.

If you replay `make configure-edge-publication` from a fresh worktree, generate
the shared static site inputs first with `make generate-changelog-portal docs`.
The edge role syncs `build/changelog-portal/` and `build/docs-portal/` as part
of the canonical public surface set.

## Controller-Local Artifacts

- `.local/coolify/root-password.txt`
- `.local/coolify/api-token.txt`
- `.local/coolify/server-key`
- `.local/coolify/server-key.pub`
- `.local/coolify/git-keys/`
- `.local/coolify/deployments/`

These files are generated or refreshed by the repo-managed automation and are not committed.

## Repo-Deploy Base Image Cache

ADR 0274 is now implemented on `coolify-lv3` through the approved profile
catalog and scheduled warm-cache surface documented in
`docs/runbooks/repo-deploy-base-image-cache.md`.

Use that runbook when:

- changing the approved base-image set for governed repo deployments
- checking whether the warm receipt is still inside the freshness bound
- verifying that `coolify-lv3` is ready for the next repo-backed deployment

## Access Model

- `coolify.lv3.org` is protected by the shared oauth2-proxy and Keycloak edge flow.
- the Coolify API is consumed from the controller through the Proxmox host Tailscale TCP proxy, not over the public edge
- `*.apps.lv3.org` is intentionally public because it is the published application ingress lane

## Operator Surfaces

Current non-chat operator entry points:

```bash
make coolify-manage ACTION=deploy-repo COOLIFY_ARGS='--repo git@github.com:baditaflorin/education_wemeshup.git --branch main --source private-deploy-key --app-name education-wemeshup --build-pack dockercompose --docker-compose-location /compose.yaml --compose-domain catalog-web=education-wemeshup.apps.lv3.org --wait'
```

```bash
python3 scripts/lv3_cli.py deploy-repo \
  --repo git@github.com:baditaflorin/education_wemeshup.git \
  --source private-deploy-key \
  --app-name education-wemeshup \
  --build-pack dockercompose \
  --docker-compose-location /compose.yaml \
  --compose-domain catalog-web=education-wemeshup.apps.lv3.org \
  --wait
```

Preferred named-profile path for repeat deployments:

```bash
make deploy-repo-profile PROFILE=education-wemeshup-production DEPLOY_PROFILE_ARGS='--wait'
```

```bash
python3 scripts/lv3_cli.py deploy-repo-profile education-wemeshup-production --wait
```

Named repo-deploy profiles live in `config/repo-deploy-catalog.json`. This is
the current bridge between the generic governed deploy contract and the future
browser intake path: operators trigger a profile by id, while the repo remains
the source of truth for repo URL, branch, build pack, compose domains, image
bundle, and verification expectations.

For the future browser-driven path, use the existing ADR 0093 ops portal and
ADR 0092 gateway as the intake surface. The portal form should submit the same
catalog-backed `deploy-repo` contract instead of inventing a second deployment
engine or depending on an assistant session.

ADR 0274 now closes the supply-path hardening gap exposed by repeated
public-registry flakeouts: the approved deployment catalog maps to a governed
base-image profile set in `config/repo-deploy-base-image-profiles.json`, and
`coolify-lv3` keeps that set warm through the cache-first contract documented
in `docs/runbooks/repo-deploy-base-image-cache.md`.
## Rollback

- revert the repo change
- rerun `make converge-coolify`
- if the public app route must be withdrawn immediately, remove the Coolify edge entries and rerun `make configure-edge-publication`
