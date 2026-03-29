# Workstream ws-0248-main-merge

- ADR: [ADR 0248](../adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md)
- Title: Integrate ADR 0248 session/logout authority into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.69
- Platform Version Observed During Merge: 0.130.47
- Release Date: 2026-03-29
- Branch: `codex/ws-0248-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0248-main-merge`
- Owner: codex
- Depends On: `ws-0248-live-apply`

## Purpose

Carry the verified ADR 0248 shared browser-session logout contract onto the
latest `origin/main` after ADR 0252 advanced the protected mainline to
repository version `0.177.68`, keep the governed live-apply wrapper aligned
with `ready_for_merge` workstreams, cut the next protected release, replay the
integrated Keycloak, Outline, and public-edge paths from that refreshed exact-
main candidate, and refresh the canonical receipt plus release truth without
rewriting ADR 0248's first-live metadata from the earlier isolated worktree
apply.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0248-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.69.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`
- `docs/workstreams/ws-0248-live-apply.md`
- `docs/runbooks/portal-authentication-by-default.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/configure-outline.md`
- `inventory/group_vars/platform.yml`
- `platform/interface_contracts.py`
- `scripts/generate_platform_vars.py`
- `scripts/session_logout_verify.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_grafana_sso_role.py`
- `tests/test_interface_contracts.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_outline_runtime_role.py`
- `tests/test_public_edge_oidc_auth_role.py`
- `tests/test_session_logout_verify.py`
- `playbooks/keycloak.yml`
- `playbooks/public-edge.yml`
- `playbooks/outline.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/grafana_sso/`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/`
- `receipts/live-applies/2026-03-28-adr-0248-session-logout-authority-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0248-session-logout-authority-mainline-live-apply.json`

## Verification

- `git fetch origin main --prune` confirmed the replay candidate stayed aligned
  with `origin/main` commit `0282291a176b0f83d90a74ba3b8ec6440aef705e`
  before the exact-main release cut. The pre-receipt source snapshot was then
  committed as `a9b0d76e93f4d9cd062b8ceeb11f99ac22397817`.
- The first guarded
  `make live-apply-service service=outline env=production ALLOW_IN_PLACE_MUTATION=true`
  attempt exposed a transient Keycloak admin-token timeout after Docker
  activity. `curl -fsS http://10.10.10.20:8091/realms/master` returned `200`
  immediately afterward, and `make converge-keycloak env=production` completed
  successfully with `docker-runtime-lv3 : ok=150 changed=0 failed=0`,
  `monitoring-lv3 : ok=17 changed=0 failed=0`,
  `nginx-lv3 : ok=39 changed=4 failed=0`,
  `postgres-lv3 : ok=47 changed=0 failed=0`, and
  `proxmox_florin : ok=201 changed=0 failed=0`.
- The guarded exact-main Outline wrapper then completed successfully with
  `docker-runtime-lv3 : ok=209 changed=5 failed=0`,
  `localhost : ok=25 changed=1 failed=0`,
  `nginx-lv3 : ok=38 changed=2 failed=0`, and
  `postgres-lv3 : ok=47 changed=0 failed=0`, proving the
  `ready_for_merge`-aware interface-contract gate, the immutable-guest
  exception path, and the repo-managed Outline publication bootstrap all worked
  from the synchronized mainline candidate.
- `make configure-edge-publication env=production` completed successfully with
  `nginx-lv3 : ok=63 changed=6 failed=0`, reloading both oauth2-proxy and
  NGINX after the exact-main logout publication refresh.
- Live HTTP verification confirmed:
  `https://home.lv3.org/.well-known/lv3/session/logout -> 302` to the shared
  oauth2-proxy sign-out path,
  `https://ops.lv3.org/.well-known/lv3/session/proxy-logout -> 302` to the
  logged-out landing page,
  `https://ops.lv3.org/.well-known/lv3/session/logged-out -> 200` with
  `Cache-Control: no-store` and `Clear-Site-Data`,
  and `curl -I https://wiki.lv3.org/ -> 200` with the expected
  Outline-compatible CSP override.
- `uv run --with playwright python scripts/session_logout_verify.py --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/outline.automation-password.txt`
  passed and reported `verified shared edge logout via https://home.lv3.org/`
  plus `verified Outline logout via https://wiki.lv3.org/auth/oidc`.
- Repo automation and validation coverage completed from this worktree:
  `./scripts/validate_repo.sh agent-standards`,
  `make validate-data-models`,
  `make syntax-check-keycloak`,
  `./scripts/validate_repo.sh generated-portals`,
  `./scripts/validate_repo.sh generated-docs`,
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`,
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/generate_diagrams.py --check`,
  `git diff --check`, and
  `uv run --with pytest --with pyyaml --with jsonschema python -m pytest ...`
  for the focused ADR 0248 auth/logout suite all passed.
- `./scripts/validate_repo.sh workstream-surfaces` remains blocked by a
  pre-existing registry defect outside this ADR: `ws-0201-main-merge` is still
  marked `ready_for_merge` without the ownership manifest that the validator now
  requires for active workstreams. The ws-0248 surfaces themselves validated up
  to that unrelated registry failure.

## Outcome

- merged ADR 0248 onto `main` in repository version `0.177.69`
- advanced the integrated platform baseline to `0.130.47` after the exact-main
  replay re-verified shared logout authority across Keycloak, oauth2-proxy, the
  edge logout surfaces, and Outline
- preserved the first isolated-worktree receipt while promoting
  `2026-03-29-adr-0248-session-logout-authority-mainline-live-apply` to the
  canonical receipt for release `0.177.69`
