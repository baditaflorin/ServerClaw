# Workstream ws-0372-live-apply: ADR 0372 Data-Driven Playbook Composition

- ADR: [ADR 0372](../adr/0372-data-driven-playbook-composition.md)
- Title: verify ADR 0372 on the governed live-apply path from the latest realistic `origin/main` base
- Status: live_applied
- Included In Repo Version: `0.178.142`
- Included In Platform Version: `0.178.142`
- Branch-Local Receipt: `receipts/live-applies/2026-04-14-adr-0372-data-driven-playbook-composition-live-apply.json`
- Implemented On: 2026-04-14
- Latest Verified Base: `origin/main@2d240e156d6407252d9178d4a0607395154831eb` (`repo 0.178.141`, `platform 0.178.141`)
- Branch: `codex/ws-0372-exact-main-r2`
- Worktree: `.worktrees/ws-0372-exact-main-r2`
- Owner: codex
- Depends On: `ADR 0021`, `ADR 0165`, `ADR 0269`, `ADR 0372`, `ADR 0373`
- Conflicts With: none

## Scope

- finish ADR 0372 on the governed service lane by proving that `make live-apply-service service=<service>` still works with the thin playbook composition model already merged on `origin/main`
- remove fresh-worktree failures that only appear when conventional runtime defaults are evaluated before `derive_service_defaults` runs
- verify the Directus live-apply path end to end, including public health checks, schema bootstrap, Keycloak-backed publication, and post-apply backup automation
- record merge-safe evidence so the latest realistic replay can be carried into integrated `main`

## Outcome

- `playbooks/vars/directus.yml` no longer re-converges `lv3.platform.keycloak_runtime` on `docker-runtime`, so the Directus live-apply lane now relies on the already-published Keycloak service on `runtime-control` instead of trying to move that runtime back onto the wrong VM.
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/defaults/main.yml` now declares the fallback controller-local artifact root plus the conventional health, ping, and OpenAPI paths that the role needs when publication verification runs from `localhost` in a fresh worktree.
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/templates/docker-compose.yml.j2` now renders explicit `extra_hosts` entries when hostname overrides are provided, which restores stable `sso.<platform-domain>` resolution during Directus OIDC discovery inside the Docker runtime.
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`, `inventory/group_vars/all/platform_services.yml`, and `tests/test_keycloak_playbook.py` now align the bootstrap path and Keycloak topology metadata with the actual `runtime-control` service placement that the platform is already running.
- `config/image-catalog.json` now points Directus at a fresh `2026-04-14` vulnerability scan receipt and a renewed exception review window, which allows the governed vulnerability budget gate to approve the replay without weakening the policy.

## Verification

- Focused regression coverage passed:
  `pytest -q tests/test_makefile_playbook_targets.py tests/test_directus_playbook.py tests/test_keycloak_playbook.py`
  returned `9 passed in 0.74s`, and
  `pytest -q tests/test_directus_playbook.py tests/test_keycloak_playbook.py`
  returned `7 passed in 0.30s`.
- The Directus image-scan receipt was refreshed in place with
  `python3 scripts/upgrade_container_image.py --image-id directus_runtime --refresh-scan-only --renew-existing-exception --write --skip-db-update --skip-artifact-cache`,
  which produced `receipts/image-scans/2026-04-14-directus-runtime.json`,
  `receipts/cve/072dcba19d51-20260414T152635Z.grype.json`, and
  `receipts/sbom/072dcba19d51.cdx.json`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=directus env=production`
  completed successfully from the exact-main worktree after the Directus publication defaults were repaired, with zero Ansible host failures across `docker-runtime`, `postgres`, `nginx`, and `localhost`.
- The governed replay verified the internal Directus health endpoint, `server/ping`, `server/specs/oas`, the schema bootstrap path, the public `https://data.<platform-domain>/server/health` endpoint, and the service-token-backed publication verification flow.
- The live-apply wrapper completed its post-apply restic trigger and updated `receipts/restic-snapshots-latest.json` at `2026-04-14T15:43:39Z`.

## Live Apply

- The latest realistic runtime-affecting base at apply time was `origin/main@2d240e156d6407252d9178d4a0607395154831eb` (`0.178.141`). While the replay was running, `origin/main` advanced to `e0134a1fe12af73f6d5efbd547a9efef5b820433` with docs-only AGENTS/CLAUDE/workstream archive updates; those later commits did not change the Directus or Keycloak runtime surfaces exercised by the replay.
- The governed Directus replay now succeeds without branch-local bypasses beyond the explicit `ALLOW_IN_PLACE_MUTATION=true` override already required by the immutable guest replacement policy for this service.
- ADR 0372 now truthfully records `Implementation Status: Live applied`,
  `Implemented In Repo Version: 0.178.142`, `Implemented In Platform Version:
  0.178.142`, and `Implemented On: 2026-04-14`.

## Integration Notes

- The remaining merge work is repository truth only: carry these verified changes onto the latest `origin/main`, bump `VERSION` and release notes to `0.178.142`, update `versions/stack.yaml` so the integrated platform truth points at the new ADR 0372 receipt, and push the integrated result to `origin/main`.
- The exact-main replay exposed two fresh-worktree gaps that were invisible on the already-converged runtime hosts: missing conventional fallback defaults in `directus_runtime`/`keycloak_runtime`, and a Directus publication verification path that assumed `directus_health_path` was always derived before `publish.yml` ran on `localhost`.
