# ADR 0194: Coolify PaaS Deploy From Repo

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.30
- Implemented In Platform Version: 0.130.35
- Implemented On: 2026-03-28
- Date: 2026-03-27

## Context

The platform already has repo-managed VM provisioning, Docker runtime automation, shared public ingress through the NGINX edge, Keycloak-backed operator authentication, and a private Gitea control-plane surface. What it does not yet have is a repo-managed self-service deployment surface that can take a Git repository and publish an application without introducing manual, one-off runtime drift.

The next platform phase explicitly calls for ingress, security, backup, and API automation work. A PaaS layer for repository deployments needs to fit the existing operating rules:

- runtime infrastructure stays version controlled
- the dashboard remains behind the shared edge OIDC boundary
- platform API access stays private and is reachable over the existing host-side Tailscale path
- public application ingress continues to terminate at the shared NGINX edge rather than bypassing it
- live deploy evidence must be captured in the repository

## Decision

We introduce Coolify as a dedicated repo-managed PaaS guest at `coolify-lv3` and expose it through two repo-managed ingress lanes:

- `https://coolify.lv3.org` for the dashboard and API, protected by the shared oauth2-proxy and Keycloak edge flow
- `https://apps.lv3.org` plus `https://*.apps.lv3.org` as the public application hostname space forwarded by the shared NGINX edge into the Coolify deployment proxy on `coolify-lv3`

### Runtime shape

- service ids: `coolify` and `coolify_apps`
- runtime host: `coolify-lv3`
- VM address: `10.10.10.70`
- VMID: `170`
- template: `lv3-docker-host`
- dashboard listen port: `8000`
- deployment proxy listen ports: `80` and `443` on the guest
- private controller/API path: Proxmox host Tailscale TCP proxy to the guest dashboard port

### Bootstrap and access model

- the Coolify VM is provisioned and converged through repo-managed Ansible
- the role installs Docker, renders the Coolify compose stack, bootstraps the initial root account, enables the API, and mints a durable personal access token
- a controller-local artifact set stores the generated root password, API token, and server registration SSH key material
- Coolify registers `coolify-lv3` itself as the managed deployment server so repo-triggered deployments stay isolated from `docker-runtime-lv3`

### Repo deployment boundary

- the repository adds a governed `lv3 deploy-repo ...` path backed by a Coolify API wrapper
- the first managed deployment contract targets Git repositories and publishes them into the wildcard `*.apps.lv3.org` edge space
- the wrapper creates or reuses the project, deployment server, and application object, then triggers deployment and waits for readiness

## Consequences

### Positive

- the platform gains a repo-managed self-hosted PaaS lane without handing public ingress directly to a new host
- application deployments stay isolated from the shared control-plane runtime guest
- operators get a private API path for automation and a browser-friendly dashboard behind the existing shared auth boundary
- wildcard application publication can be managed once at the edge instead of per-app DNS and certificate work

### Trade-offs

- Coolify adds a new control-plane component with its own bootstrap and lifecycle surface
- the shared edge now carries a wildcard application route that must remain carefully scoped to Coolify-owned hostnames
- the first implementation focuses on repo-driven application deploys and not the full upstream Coolify feature set

## Repository Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_coolify_playbook.py tests/test_coolify_runtime_role.py tests/test_coolify_tool.py tests/test_generate_platform_vars.py tests/test_nginx_edge_publication_role.py tests/test_lv3_cli.py tests/test_service_topology_filters.py tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_edge_publication_playbooks.py -q` passed with `98 passed in 2.45s` on 2026-03-28 after reconciling the authenticated-edge expectations from the ADR 0197 mainline merge.
- `./scripts/validate_repo.sh agent-standards` passed on 2026-03-28 from `codex/ws-0194-main-merge` after registering the dedicated main-merge branch in `workstreams.yaml`.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `uv run --with pyyaml python scripts/subdomain_exposure_audit.py --check-registry`, `uv run --with jsonschema python scripts/generate_dependency_diagram.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, `python3 scripts/generate_status_docs.py --check`, `python3 scripts/generate_diagrams.py --check`, and `git diff --check` all passed on 2026-03-28.

## Live Apply Note

Live apply completed first from `codex/ws-0194-live-apply` and then was replayed from merged mainline on `codex/ws-0194-main-merge` commit `093af353` on 2026-03-28.

- `make converge-coolify` completed successfully from the merged-main candidate with `coolify-lv3 ok=115 changed=7 failed=0`, `nginx-lv3 ok=71 changed=5 failed=0`, and `proxmox_florin ok=43 changed=5 failed=0`.
- `python3 scripts/coolify_tool.py whoami` confirmed the private controller path at `http://100.64.0.1:8012`, public dashboard URL `https://coolify.lv3.org`, app space `https://apps.lv3.org`, and a reachable plus usable local deployment server `coolify-lv3`.
- `python3 scripts/coolify_tool.py deploy-repo --repo https://github.com/coollabsio/coolify-examples --branch main --base-directory /static --app-name repo-smoke --build-pack static --subdomain repo-smoke --wait --timeout 900` finished successfully on the merged-main replay with deployment `klmsg3ybgvp7xwnk8op3cdlp` for application `r4z9zeqpci7uykiw3bj08hrf`.
- Direct public-edge verification against `65.108.75.123` showed `https://coolify.lv3.org` returning the expected oauth2-proxy `302` challenge, `https://repo-smoke.apps.lv3.org` returning `200` with the expected example-page content, and `https://apps.lv3.org` returning `404` while no default apex app is assigned.
- The canonical platform-version evidence now lives in `receipts/live-applies/2026-03-28-adr-0194-coolify-paas-deploy-from-repo-mainline-live-apply.json`, which supersedes the earlier branch-local receipt while preserving it for workstream history.

## Related ADRs

- ADR 0025: Compose-managed runtime stacks
- ADR 0056: Keycloak SSO broker
- ADR 0143: Private Gitea for repo-managed platform source control
- ADR 0176: Inventory sharding and host-scoped Ansible execution
