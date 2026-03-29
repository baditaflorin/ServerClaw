# Workstream WS-0235: Cross-Application Launcher Live Apply

- ADR: [ADR 0235](../adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md)
- Title: Cross-application launcher and favorites via a PatternFly-style shared masthead launcher in the interactive ops portal
- Status: live_applied
- Implemented In Repo Version: 0.177.69
- Live Applied In Platform Version: 0.130.45
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0235-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0152-homepage`, `adr-0209-use-case-services`, `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `config/service-capability-catalog.json`, `config/workflow-catalog.json`, `config/persona-catalog.json`, `docs/runbooks/platform-operations-portal.md`, `tests/test_interactive_ops_portal.py`, `workstreams.yaml`, `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`, `receipts/live-applies/`

## Scope

- add a shared masthead launcher to the interactive ops portal as the first live implementation of ADR 0235
- render launcher destinations from canonical service, publication, workflow, and persona metadata instead of hard-coded bookmark lists
- support search, favorites, and recent destinations in a way that can be verified through repo tests and live platform checks
- document the operator usage and leave merge-to-main integration notes explicit if protected release files must wait

## Non-Goals

- rewriting every first-party surface into a full PatternFly application in one workstream
- changing the protected release files on this workstream branch unless this branch becomes the final merge-to-main integration step
- replacing Homepage or third-party product-native interfaces

## Expected Repo Surfaces

- `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0235-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `.config-locations.yaml`
- `config/service-capability-catalog.json`
- `config/workflow-catalog.json`
- `config/persona-catalog.json`
- `docs/schema/persona-catalog.schema.json`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/service_catalog.py`
- `scripts/validate_repository_data_models.py`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-live-apply.json`

## Expected Live Surfaces

- `https://ops.lv3.org` exposes the shared application launcher in the masthead
- the launcher groups destinations by purpose, allows persona-aware filtering, and records favorites plus recent destinations
- favorites and recents can be re-verified against the live portal session without ad hoc server edits

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal.py tests/test_runtime_assurance_scoreboard.py -q`
- `python3 -m py_compile scripts/ops_portal/app.py scripts/service_catalog.py scripts/validate_repository_data_models.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make syntax-check-ops-portal`
- `./scripts/validate_repo.sh agent-standards`
- `make immutable-guest-replacement-plan service=ops_portal`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-live-apply'`
- guest-local verification of `/health`, `/`, `/partials/overview`, `/partials/launcher`, launcher favorites, launcher recents, and the public `https://ops.lv3.org` edge

## Live Apply Outcome

- the first governed production replay failed closed exactly as ADR 0191 intends: `make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-live-apply'` exited before replay and instructed the operator to use immutable replacement or rerun with the documented narrow exception `ALLOW_IN_PLACE_MUTATION=true`
- `make immutable-guest-replacement-plan service=ops_portal` confirmed the exception rule for `docker-runtime-lv3`: only use in-place mutation for a narrow reversible change and record the exception in the live-apply receipt plus workstream notes
- the next replay with `ALLOW_IN_PLACE_MUTATION=true` exposed a real concurrency hazard instead of a feature defect: a competing branch-local `ops_portal` apply rewrote `/opt/ops-portal/service` mid-run, leaving `/partials/launcher` at `404`, `docker logs ops-portal` full of launcher 404s, and `/opt/ops-portal/service/ops_portal/app.py` at hash `ceb70927becdeab1a391c4b710bc1c094f4c9de24a94501151217ad8bbc43874` with no launcher route
- after obtaining an uncontended replay window, `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-live-apply'` completed successfully with final recap `docker-runtime-lv3 ok=126 changed=22 failed=0 skipped=17`
- the hardened runtime verify now checks the launcher partial locally during replay, and the successful run passed both `Verify the application launcher partial renders locally` and `Assert the application launcher is present`
- guest-side proof now matches the ws-0235 checkout: `/opt/ops-portal/service/ops_portal/app.py` hash `cf6ddb19b3353f718b5933cb589d6a3d1c3ae7377ceda033ed0e29e4bcfcc7ba`, `/opt/ops-portal/service/search_fabric/__init__.py` hash `d9094470c32e2f93c71ba5b3eb4f2df7737186ec4e9299adb660a83e0194e904`, `/opt/ops-portal/data/config/workflow-catalog.json` hash `3e9131c2beda07a91e4a419a8d5d1729ff92749be840f4fedb718f100c6a34c9`, `/opt/ops-portal/data/config/persona-catalog.json` hash `86819853d16693a72c2d5119690043b66f8db825d43ce4a5b6873bb52437033b`, and `@app.get("/partials/launcher", response_class=HTMLResponse)` appears at line `1324`
- internal verification showed `/health`, `/`, `/partials/overview`, and `/partials/launcher` all returning `200`, with the launcher body containing `Application Launcher`, `Switch tools without leaving the shared shell`, and `Search destinations, pin favorites, and reopen recent paths from one shared masthead control.`
- a cookie-backed guest-local launcher session verified favorites and recents end to end: `before_favorites=1`, `before_recents=0`, `after_favorites=1`, `after_recents=1`, `after_keycloak_mentions=7`, and `/launcher/go/service%3Akeycloak` returned `303`
- public-edge verification confirmed `https://ops.lv3.org/health` returned `200 {"status":"ok"}` and `https://ops.lv3.org/` preserved the expected `302` redirect to `https://ops.lv3.org/oauth2/sign_in?rd=https://ops.lv3.org/`

## Live Evidence

- live-apply receipt: `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-live-apply.json`
- guest hash proof: `receipts/live-applies/evidence/2026-03-29-adr-0235-live-hashes.txt`
- internal endpoint proof: `receipts/live-applies/evidence/2026-03-29-adr-0235-internal-endpoints.txt`
- launcher session proof: `receipts/live-applies/evidence/2026-03-29-adr-0235-launcher-session-check.txt`
- public-edge proof: `receipts/live-applies/evidence/2026-03-29-adr-0235-public-edge-check.txt`

## Mainline Integration Notes

- release `0.177.69` is the first merged repo version that carries ADR 0235 on
  `origin/main`
- the exact-main replay from
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-main-merge-r3`
  re-verified the launcher on `2026-03-29` with final recap
  `docker-runtime-lv3 ok=129 changed=14 failed=0 skipped=14`
- the current live platform baseline after that exact-main replay is
  `0.130.47`
