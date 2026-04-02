# Workstream ws-0281-live-apply: Live Apply ADR 0281 From Latest `origin/main`

- ADR: [ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
- Title: Replace the partial ad hoc GlitchTip install with a repo-managed Sentry-compatible error tracking service, instrument first-party producers, and verify the live stack end to end
- Status: blocked
- Included In Repo Version: latest realistic `origin/main` replay base `0.177.142`
- Branch-Local Receipt: `receipts/live-applies/2026-04-01-adr-0281-glitchtip-mainline-live-apply.json` records the current partial exact-main outcome; historical first-live receipt `receipts/live-applies/2026-03-30-adr-0281-glitchtip-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-01-adr-0281-glitchtip-mainline-live-apply.json` (currently partial and intentionally blocked on shared-host quiet-window contention)
- Live Applied In Platform Version: first implementation `0.130.69`; latest fully verified mainline platform truth still `0.130.82` because the exact-main `0.177.132` public verification timed out before completion
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Latest origin/main Base: `0.177.142` at `67bc9f13f973f5386b1ec5b4dd4304e400c214a8`
- Branch: `codex/ws-0281-mainline-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0281-mainline-v2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication-at-the-nginx-edge`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secrets-injection-pattern`, `adr-0130-mail-platform-for-transactional-email`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0281-live-apply.md`, `docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md`, `docs/runbooks/configure-glitchtip.md`, `receipts/live-applies/`, `playbooks/glitchtip.yml`, `playbooks/services/glitchtip.yml`, `collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/`, `collections/ansible_collections/lv3/platform/roles/glitchtip_postgres/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `build/platform-manifest.json`, `config/`, `scripts/`, `tests/`, `Makefile`

## Scope

- introduce a repo-managed GlitchTip service published at `errors.lv3.org`
- move the service onto the shared PostgreSQL, Keycloak, OpenBao, and NGINX platform patterns
- replace the unstable ad hoc runtime on `docker-runtime-lv3` with an automation-owned deployment
- instrument first-party producers so GlitchTip receives real Sentry-compatible events
- verify the branch-local live apply from the latest synchronized `origin/main` and record the evidence

## Non-Goals

- opportunistically bumping `VERSION`, release sections in `changelog.md`, the integrated `README.md` summary, or `versions/stack.yaml` outside the exact-main integration step; this worktree is now rebased onto `origin/main` `0.177.142`, but the exact-main live replay and protected canonical-truth update still have not completed truthfully
- claiming a broader production-readiness posture beyond the ADR 0281 error-tracking scope
- rewriting unrelated platform services or replacing existing Loki, Tempo, Langfuse, or Grafana responsibilities

## Expected Repo Surfaces

- `playbooks/glitchtip.yml`
- `playbooks/services/glitchtip.yml`
- `build/platform-manifest.json`
- `collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/`
- `collections/ansible_collections/lv3/platform/roles/glitchtip_postgres/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/`
- `scripts/`
- `tests/`
- `Makefile`
- `docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md`
- `docs/runbooks/configure-glitchtip.md`
- `docs/workstreams/ws-0281-live-apply.md`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime-lv3` runs the GlitchTip application and its supporting runtime containers under repo-managed automation
- `postgres-lv3` hosts the `glitchtip` database under the shared PostgreSQL management model
- `errors.lv3.org` is published through the NGINX edge with a valid HTTPS response
- Keycloak OIDC login works for GlitchTip admin access
- first-party producers can send Sentry-compatible events that appear in GlitchTip projects

## Ownership Notes

- this workstream owns the branch-local ADR 0281 implementation, live-apply verification, and receipts
- the current host already contains a partial manual GlitchTip install; replacing or reconciling it must preserve useful state without treating the ad hoc compose files as canonical truth
- protected release files remain deferred until the later main integration step, even if the branch-local live apply completes successfully
- the handoff must state the exact merge-to-main follow-through still required after the live apply is verified

## Latest-Main Replay Status

- The branch is now freshly rebased onto latest realistic `origin/main` `67bc9f13f973f5386b1ec5b4dd4304e400c214a8` at repository version `0.177.142`.
- The exact-main replay initially failed in the shared Docker bridge-chain helper after Docker recovered its publication chains. This branch hardens that helper and the dependent Keycloak, JupyterHub, and Superset assertions, with focused regression evidence in `receipts/live-applies/evidence/2026-04-01-adr-0281-docker-bridge-chain-fix-tests-r2-0.177.132.txt` (`61 passed`).
- The corrected exact-main replay (`receipts/live-applies/evidence/2026-04-01-adr-0281-mainline-live-apply-r2-0.177.132.txt`) reconverged PostgreSQL, Docker runtime recovery, Keycloak, the GlitchTip runtime, repo-managed bootstrap, and NGINX edge publication, then spent a full 30-minute budget waiting for a controller-local quiet window before public verification.
- That first quiet-window wait timed out behind concurrent `ws-0303-main-integration` and `ws-0286-live-apply-r2` playbooks on shared hosts. When the playbook entered a second 30-minute retry wait, the replay was manually stopped to avoid holding shared-host capacity open. After rebasing onto `0.177.142`, the shared hosts are still not safe to touch: a fresh 15-minute waiter timed out while `ws-0247-latest-main`, `ws-0289-label-studio-live-apply-r1`, `ws-0299-live-apply`, `ws-0303-main-integration`, `ws-0304-mainline`, `ws-0308-live-apply-r2`, `ws-0309-main-integration`, `ws-0312-live-apply`, and `ws-0314-live-apply` kept mutating `postgres-lv3`, `docker-runtime-lv3`, and `nginx-lv3`; see `receipts/live-applies/evidence/2026-04-02-adr-0281-mainline-quiet-window-waiter-r2-0.177.142.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-mainline-manual-stop-r1-0.177.132.txt`, and `receipts/live-applies/evidence/2026-04-01-adr-0281-mainline-quiet-window-probe-r3-0.177.132.txt`.
- The branch now carries a truthful partial exact-main receipt in `receipts/live-applies/2026-04-01-adr-0281-glitchtip-mainline-live-apply.json`; `scripts/live_apply_receipts.py --validate` passes against it, proving the branch-local canonical receipt state is internally consistent even though the live verification is blocked.
- The same branch still retains earlier same-worktree proof that `errors.lv3.org` served the correct TLS certificate, returned `HTTP/2 200` for public health and auth config, exposed the `LV3 Keycloak` OIDC handoff, and accepted a platform-findings smoke event before the `0.177.132` release cut. See `receipts/live-applies/evidence/2026-04-01-adr-0281-current-public-surface-r2-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-public-auth-config-r1-0.177.129.txt`, and `receipts/live-applies/evidence/2026-04-01-adr-0281-event-smoke-r2-0.177.129.txt`.
- The rebased repo validation picture is current again on `0.177.142`. Focused regression coverage is preserved in `receipts/live-applies/evidence/2026-04-02-adr-0281-targeted-latest-main-tests-r1-0.177.142.txt` (`42 passed`), `make check-build-server` passes in `receipts/live-applies/evidence/2026-04-02-adr-0281-mainline-check-build-server-r1-0.177.142.txt`, and `make remote-validate` passes in `receipts/live-applies/evidence/2026-04-02-adr-0281-mainline-remote-validate-r1-0.177.142.txt`.
- The rebased local validation bundle also exposed one rebase-drift issue that is now fixed on this branch: `config/ansible-role-idempotency.yml` carried a stale duplicate `livekit_runtime` key after mainline moved. Removing that duplicate restored `yaml-lint` to green for the cleaned tree.
- `make validate` now narrows only to protected canonical truth on the top-level `README.md`, and the dedicated check in `receipts/live-applies/evidence/2026-04-02-adr-0281-mainline-canonical-truth-r1-0.177.142.txt` confirms that `README.md` is the only stale canonical surface. The matching full push-path receipt `receipts/live-applies/evidence/2026-04-02-adr-0281-mainline-pre-push-gate-r1-0.177.142.txt` shows every other `pre-push-gate` lane passed on the cleaned tree, with `generated-docs` failing only because canonical truth wants to rewrite `README.md`.
- Fresh read-only public checks on 2026-04-02 still show the live edge is drifted: at 11:11:11 GMT, `errors.lv3.org` returned `HTTP/2 308` to `https://nginx.lv3.org/health/` and served certificate `CN=nginx.lv3.org`; see `receipts/live-applies/evidence/2026-04-02-adr-0281-current-public-surface-r2-0.177.142.txt` and `receipts/live-applies/evidence/2026-04-02-adr-0281-current-public-cert-r2-0.177.142.txt`.

## Verification

- `uv run --with pytest python -m pytest -q`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- `./scripts/validate_repo.sh agent-standards`
- `make live-apply-service service=glitchtip env=production`
- branch-local SSH, HTTP, and API checks proving publication, health, OIDC, and event ingestion end to end

## Branch-Local Results

- `receipts/live-applies/evidence/2026-04-01-ws-0281-converge-glitchtip-r1-0.177.129.txt`
  captures the governed latest-main replay through PostgreSQL, Docker runtime,
  Keycloak recovery, GlitchTip bootstrap, and NGINX edge publication. The
  automated quiet-window publication verifier never cleared because unrelated
  concurrent workstreams kept touching `docker-runtime-lv3` and `nginx-lv3`, so
  the waiting verifier was manually stopped after independent public
  verification succeeded; see
  `receipts/live-applies/evidence/2026-04-01-adr-0281-quiet-window-manual-stop-r1-0.177.129.txt`.
- Fresh public verification preserved in
  `receipts/live-applies/evidence/2026-04-01-adr-0281-current-public-surface-r2-0.177.129.txt`
  and
  `receipts/live-applies/evidence/2026-04-01-adr-0281-public-auth-config-r1-0.177.129.txt`
  confirmed `errors.lv3.org` resolves to `65.108.75.123`, serves
  `CN=errors.lv3.org`, returns `HTTP/2 200` on the public health and auth
  endpoints, and advertises the repo-managed Keycloak OIDC provider.
- Fresh end-to-end ingestion verification preserved in
  `receipts/live-applies/evidence/2026-04-01-adr-0281-event-smoke-r2-0.177.129.txt`
  confirmed the live public DSN path creates issue `PLATFORM-FINDINGS-7` for
  event `dcddc4c934064775b3aad2f01b293aec`.
- `receipts/live-applies/2026-03-30-adr-0281-glitchtip-live-apply.json`
  records the synchronized branch-local replay from committed source
  `229fd0933019701297b96259aef6a9b6beecfdcd` on repository version
  `0.177.104` and live platform version `0.130.69`.
- `make converge-glitchtip` completed successfully from the rebased latest-main
  tree with final recap `docker-runtime-lv3 : ok=261 changed=5 failed=0
  skipped=60`, `postgres-lv3 : ok=51 changed=0 failed=0 skipped=14`,
  `nginx-lv3 : ok=40 changed=5 failed=0 skipped=6`, and `localhost : ok=27
  changed=0 failed=0 skipped=5`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-glitchtip-final6.txt`.
- Fresh public verification preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-glitchtip-public-verification.txt`
  confirmed `errors.lv3.org` resolves to `65.108.75.123`, the shared edge now
  renders dedicated `server_name errors.lv3.org` blocks, the public health
  endpoint returns `{"healthy": {}, "problems": []}`, the GlitchTip auth
  config advertises the repo-managed Keycloak OIDC provider, and an end-to-end
  smoke event landed in the `platform-findings` project.
- `make converge-mail-platform` and `make converge-windmill` were replayed
  after the GlitchTip bootstrap to refresh producer consumers, with successful
  evidence in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-mail-platform.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-windmill.txt`.
- Fresh producer checks preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-mail-gateway-sentry-env.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0281-windmill-runtime-evidence.txt`
  confirmed the reconverged `lv3-mail-gateway` runtime exports
  `SENTRY_DSN=https://<redacted>@errors.lv3.org/1`,
  `SENTRY_ENVIRONMENT=production`, and `SENTRY_RELEASE=0.177.56`, while the
  Windmill runtime still exposes its expected `LV3_GRAPH_DSN` env and the
  branch-local `windmill-jobs.dsn` artifact exists under the shared controller
  secret root.
- The rebased branch validation bundle also passed: targeted pytest returned
  `70 passed`, `make syntax-check-glitchtip` passed, and
  `./scripts/validate_repo.sh agent-standards`,
  `./scripts/validate_repo.sh ansible-idempotency`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `uv run --with pyyaml python scripts/live_apply_receipts.py --validate`
  all completed successfully from this latest-main worktree.
- The first DNS replay happened during the Hetzner legacy DNS brownout window,
  so the `errors` A record was bridged manually before the new retry handling
  landed. The final synchronized replay now observes the canonical `errors ->
  65.108.75.123` state without further manual mutation.
- During branch-local verification, the public edge had drifted back to the
  default `nginx.lv3.org` redirect because a later shared-edge replay no
  longer carried the GlitchTip publication surface. Rerunning the governed
  GlitchTip workflow from this latest-main worktree restored the dedicated edge
  blocks and revalidated the public auth and smoke path.

## Outcome

- The branch now contains the exact-main bridge-chain hardening, the rebased latest-main replay state for `0.177.142`, repaired GlitchTip Keycloak defaults and test expectations, deduped idempotency metadata, cleaned generated artifacts, a truthful partial mainline receipt, and current blocker evidence showing that shared-host concurrency plus live public-surface drift, not repository integration, stopped the final honest verification step.
- Merge is blocked on three fronts: the exact-main public verification still needs a quiet window clear of current `ws-0247`, `ws-0289`, `ws-0299`, `ws-0303`, `ws-0304`, `ws-0308`, `ws-0309`, `ws-0312`, and `ws-0314` activity on `postgres-lv3`, `docker-runtime-lv3`, and `nginx-lv3`; the read-only public edge currently serves `CN=nginx.lv3.org` and redirects `errors.lv3.org` to `nginx.lv3.org`; and both `make validate` plus `make pre-push-gate` now narrow only to the protected canonical-truth rewrite for the top-level `README.md`.
- The next agent should retry the exact-main GlitchTip live apply only inside a real quiet window from this rebased `0.177.142` tree, re-check the public `errors.lv3.org` surface from the integrated tree, update platform truth only if that replay really verifies end to end, confirm the existing `make remote-validate`, `make validate`, `make pre-push-gate`, and `make check-build-server` receipts remain current against latest main, and only then merge/push `main` and delete this worktree.

## Merge Criteria

- the repo owns the GlitchTip runtime, database wiring, publication, OIDC client, and secret injection path
- at least one first-party producer is instrumented and verified against the live GlitchTip service
- ADR 0281 metadata, runbook guidance, workstream notes, and live-apply receipts clearly describe what is true on the branch and what remains for merge to `main`
