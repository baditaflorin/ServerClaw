# Workstream ws-0372-live-apply: ADR 0372 Data-Driven Playbook Composition

- ADR: [ADR 0372](../adr/0372-data-driven-playbook-composition.md)
- Title: close ADR 0372 on the governed Directus live-apply lane from the latest realistic `origin/main`
- Status: merged
- Included In Repo Version: `0.178.144`
- Included In Platform Version: `0.178.144`
- Branch-Local Receipt: `receipts/live-applies/2026-04-14-adr-0372-data-driven-playbook-composition-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-15-adr-0372-data-driven-playbook-composition-mainline-live-apply.json`
- Implemented On: 2026-04-15
- Live Applied On: 2026-04-15
- Live Applied In Platform Version: `0.178.144`
- Latest Verified Base: `origin/main@d86bd43709f5319338def284988a907559ff9f9c` (`repo 0.178.143`, `platform 0.178.143`)
- Branch: `codex/ws-0372-exact-main-r2`
- Worktree: removed after merge-to-main
- Owner: codex
- Depends On: `ADR 0021`, `ADR 0165`, `ADR 0269`, `ADR 0372`, `ADR 0373`
- Conflicts With: none

## Scope

- replay the governed `make live-apply-service service=directus` lane from a fresh exact-main worktree so ADR 0372 is proven on the real service path rather than only by merged code and syntax checks
- close the fresh-worktree runtime gaps exposed by that replay: missing Directus and Keycloak conventional defaults, a stale Keycloak publication topology pointer, and Directus hostname override handling during OIDC discovery
- promote the verified replay into integrated repo and platform truth, including the protected release surfaces, workstream archive state, and live-apply receipts

## Outcome

- `playbooks/vars/directus.yml` now keeps the Directus live-apply lane focused on `docker_runtime` plus `directus_runtime`; it no longer tries to re-converge `lv3.platform.keycloak_runtime` on `docker-runtime` after Keycloak had already been moved to `runtime-control`.
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/defaults/main.yml` now declares the controller-local artifact root and the conventional `health`, `ping`, and OpenAPI paths required when publication verification runs from `localhost` in a fresh worktree.
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/tasks/main.yml` now resolves the bootstrap helper from the collection-aware playbook path, and `collections/ansible_collections/lv3/platform/roles/directus_runtime/templates/docker-compose.yml.j2` now renders explicit `extra_hosts` entries when public hostname overrides are provided so `sso.<platform-domain>` resolves correctly during Directus OIDC discovery inside the container.
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`, `inventory/group_vars/all/platform_services.yml`, and `tests/test_keycloak_playbook.py` now align the Keycloak runtime metadata with the real `runtime-control` placement already running on the platform.
- `config/image-catalog.json` now points Directus at the refreshed `2026-04-14` image scan and renewed exception window, allowing the governed vulnerability budget gate to approve the replay without weakening the policy.
- The final closeout updates the protected integration surfaces only at merge time: `VERSION`, `RELEASE.md`, `docs/release-notes/0.178.144.md`, `README.md`, `versions/stack.yaml`, the archived workstream shard, and the integrated receipts now all agree on repo and platform version `0.178.144`.

## Verification

- Focused ADR 0372 regression coverage passed on the latest exact-main candidate:
  `pytest -q tests/test_makefile_playbook_targets.py tests/test_directus_playbook.py tests/test_directus_runtime_role.py tests/test_keycloak_playbook.py tests/test_keycloak_runtime_role.py tests/test_adr_0374_hairpin_runtime_templates.py tests/test_directus_bootstrap.py`
  returned `54 passed in 3.14s`; evidence:
  `receipts/live-applies/evidence/2026-04-15-ws-0372-mainline-pytest-r1-0.178.143.txt`.
- The Directus image scan was refreshed in place and the governed policy inputs were renewed via `receipts/image-scans/2026-04-14-directus-runtime.json`, `receipts/cve/072dcba19d51-20260414T152635Z.grype.json`, and `receipts/sbom/072dcba19d51.cdx.json`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=directus env=production` completed successfully from the latest realistic mainline candidate, with a clean Directus replay across `docker-runtime`, `postgres`, `nginx`, and `localhost`; evidence:
  `receipts/live-applies/evidence/2026-04-15-ws-0372-mainline-directus-live-apply-r1-0.178.143.txt`.
- The governed replay verified the internal Directus health endpoint, `server/ping`, `server/specs/oas`, the schema bootstrap path, the public `https://data.<platform-domain>/server/health` endpoint, and the token-backed publication verification flow. The wrapper also completed its post-apply restic trigger and recorded `receipts/restic-backups/20260415T071036Z.json`, which updated `receipts/restic-snapshots-latest.json`.
- The integrated candidate also passes the final repo gates, live-apply receipt validation, `git diff --check`, build-server reachability, and `make remote-validate`; the matching evidence is recorded under the `2026-04-15-ws-0372-mainline-final-*.txt` transcripts in `receipts/live-applies/evidence/`.

## Live Apply

- The first exact-main replay for this closeout ran from `origin/main@2d240e156d6407252d9178d4a0607395154831eb` with repo and platform version `0.178.141`, proving the Directus lane on the latest realistic runtime-affecting base that existed when ws-0372 entered live-apply verification.
- The final promotion replay was re-run from `origin/main@d86bd43709f5319338def284988a907559ff9f9c`, the latest realistic base at merge time, with repo and platform version `0.178.143`. That replay is what promoted the Directus receipt into integrated platform version `0.178.144`.
- The only apply-time override remained the governed `ALLOW_IN_PLACE_MUTATION=true` switch already required by the immutable guest replacement policy for Directus. No branch-local bypasses or manual server edits were needed.

## Integration Notes

- ADR 0372 first became true in repo version `0.178.136`; this closeout does not change that history. What it adds is the verified platform truth: Directus now has a governed exact-main replay and an integrated mainline replay recorded in repo and platform version `0.178.144`.
- The exact-main replay exposed two gaps that were invisible on already-converged hosts: missing conventional fallback defaults in `directus_runtime` and `keycloak_runtime`, and a Directus publication verification path that needed explicit hostname override rendering for stable SSO discovery inside the container.
- The verified feature branch was promoted to `main` and `origin/main`, after which the temporary ws-0372 worktrees were removed.
