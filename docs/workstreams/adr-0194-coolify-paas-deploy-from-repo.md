# Workstream ADR 0194: Coolify PaaS Deploy From Repo

- ADR: [ADR 0194](../adr/0194-coolify-paas-deploy-from-repo.md)
- Title: Repo-managed Coolify on `coolify-lv3` with private API access, protected dashboard publication, and wildcard app ingress
- Status: live_applied
- Branch: `codex/ws-0194-live-apply`
- Worktree: `.worktrees/ws-0194-live-apply`
- Owner: codex
- Depends On: `adr-0025-docker-compose-stacks`, `adr-0056-keycloak-sso`, `adr-0143-private-gitea`, `adr-0176-inventory-sharding`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `roles/nginx_edge_publication`, `config/service-capability-catalog.json`, `scripts/generate_platform_vars.py`, `scripts/subdomain_catalog.py`

## Scope

- add the dedicated `coolify-lv3` guest, network policy, host proxy lane, and service topology entries
- add the repo-managed `coolify_runtime` role plus `playbooks/coolify.yml`
- publish the dashboard at `coolify.lv3.org` behind the shared edge OIDC boundary
- publish the application proxy space at `apps.lv3.org` and `*.apps.lv3.org`
- add the governed `lv3 deploy-repo` wrapper backed by the Coolify API
- document bootstrap, verification, and rollback in `docs/runbooks/configure-coolify.md`

## Non-Goals

- making shared integration-file truth changes on this workstream branch
- replacing existing `docker-runtime-lv3` application services with Coolify-managed deployments
- broad private-repository bootstrap beyond the first governed repo deployment path

## Expected Repo Surfaces

- `docs/adr/0194-coolify-paas-deploy-from-repo.md`
- `docs/workstreams/adr-0194-coolify-paas-deploy-from-repo.md`
- `docs/runbooks/configure-coolify.md`
- `playbooks/coolify.yml`
- `playbooks/services/coolify.yml`
- `collections/ansible_collections/lv3/platform/roles/coolify_runtime/`
- `inventory/host_vars/proxmox_florin.yml`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `scripts/coolify_tool.py`
- `scripts/validate_repo.sh`
- `scripts/lv3_cli.py`
- `receipts/live-applies/2026-03-28-adr-0194-coolify-paas-deploy-from-repo-live-apply.json`

## Expected Live Surfaces

- `coolify-lv3` exists, is reachable over SSH, and runs the Coolify stack
- `https://coolify.lv3.org` redirects through the shared edge OIDC boundary
- the private controller path reaches the Coolify API through the host Tailscale proxy
- one repo deployment succeeds end to end and becomes reachable at `https://<name>.apps.lv3.org`

## Verification

- `make syntax-check-coolify`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_coolify_playbook.py tests/test_coolify_runtime_role.py tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_nginx_edge_publication_role.py tests/test_generate_platform_vars.py tests/test_lv3_cli.py tests/test_service_topology_filters.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/uptime_contract.py --check`
- `python3 scripts/subdomain_exposure_audit.py --check-registry`
- `scripts/validate_repo.sh yaml ansible-syntax role-argument-specs shell json data-models workstream-surfaces agent-standards`

## Merge Criteria

- the Coolify VM converges repeatably from repo automation
- the dashboard is edge-protected and the wildcard app hostname lane routes correctly through the shared edge
- the repo-managed API wrapper can create or update an app deployment from a Git repository
- live verification proves dashboard access control, private API reachability, and one successful repo deployment

## Outcome

Live apply completed on 2026-03-28.

- `make converge-coolify` completed successfully and converged the Proxmox guest, private controller path, and NGINX edge publication.
- `coolify-proxy` is now present on `coolify-lv3` and binds guest ports `80`, `443`, and `8080`, while the Coolify dashboard remains on `8000`.
- `python3 scripts/coolify_tool.py whoami` confirmed the private controller path, public dashboard URL, and the registered local deployment server as reachable and usable.
- `python3 scripts/coolify_tool.py deploy-repo ... --app-name repo-smoke --subdomain repo-smoke --wait` completed successfully with deployment `a13akq7v9de7vyqo5u33pz0y`.
- Direct edge probes with `--resolve` confirmed `coolify.lv3.org` returned the expected auth-boundary `302` and `repo-smoke.apps.lv3.org` returned `200`.
- `apps.lv3.org` currently returns `404`, which is expected until an apex application is assigned.
- `dig +short` from the controller returned no public answers for the Coolify hostnames at verification time, so the branch records successful direct edge verification separately from DNS propagation.
- `./scripts/validate_repo.sh agent-standards` now passes cleanly after fixing the zero-match arithmetic and branch-registry checks in `scripts/validate_repo.sh`.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` still fails on this workstream branch because `versions/stack.yaml` is intentionally protected until the final merge-to-main integration step.

## Notes For The Next Assistant

- Do not bump `VERSION`, touch release sections in `changelog.md`, or update `versions/stack.yaml` on this branch.
- Merge-to-main still needs the protected integration updates: `VERSION`, release notes in `changelog.md`, the top-level integrated status summary in `README.md`, and the canonical observed-state plus platform-version update in `versions/stack.yaml`.
- Regenerate the shared generated portals from merged `main` during the final integration step instead of carrying forward the branch-local copied `build/docs-portal` and `build/changelog-portal` artifacts.
- Preserve the live-apply receipt at `receipts/live-applies/2026-03-28-adr-0194-coolify-paas-deploy-from-repo-live-apply.json` when merging so the direct-edge verification and DNS caveats remain attached to the workstream evidence.
