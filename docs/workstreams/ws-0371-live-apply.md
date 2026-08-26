# Workstream ws-0371-live-apply: ADR 0371 Parameterized Service Verification Tasks

- ADR: [ADR 0371](../adr/0371-parameterized-verify-tasks.md)
- Title: re-verify parameterized service verification tasks from latest origin/main
- Status: merged
- Included In Repo Version: `0.178.143`
- Included In Platform Version: `0.178.143`
- Branch-Local Receipt: `receipts/live-applies/2026-04-14-adr-0371-parameterized-service-verification-tasks-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-14-adr-0371-parameterized-service-verification-tasks-mainline-live-apply.json`
- Promotion Gate Waiver: `receipts/gate-bypasses/20260414T180616Z-codex-ws-0371-live-apply-dbe0269-skip-remote-gate.json`
- Implemented On: 2026-04-14
- Live Applied On: 2026-04-14
- Live Applied In Platform Version: `0.178.143`
- Latest Verified Base: `origin/main@7b72694975ef8aae83e59d96c08dd27181595b2e` (`repo 0.178.142`, `platform 0.178.141`)
- Branch: `codex/ws-0371-live-apply`
- Worktree: removed after merge-to-main
- Owner: codex
- Depends On: `ADR 0165`, `ADR 0289`, `ADR 0371`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health_extra.yml`, `collections/ansible_collections/lv3/platform/roles/librechat_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/litellm_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/repowise_runtime/tasks/verify.yml`, `config/health-probe-catalog.json`, `config/service-capability-catalog.json`, `docs/adr/0371-parameterized-verify-tasks.md`, `docs/runbooks/live-apply-receipts-and-verification-evidence.md`, `playbooks/services/librechat.yml`, `playbooks/services/litellm.yml`, `playbooks/services/repowise.yml`, `platform/ansible/execution_scopes.py`, `receipts/live-applies/*adr-0371*`, `receipts/live-applies/evidence/*ws-0371*`, `scripts/generate_diagrams.py`, `scripts/generate_ops_portal.py`, `scripts/generate_status_docs.py`, `scripts/platform_manifest.py`, `tests/test_ansible_execution_scopes.py`, `tests/test_service_live_apply_wrappers.py`, `workstreams/archive/2026/ws-0371-live-apply.yaml`, `workstreams.yaml`

## Scope

- confirm the latest `origin/main` state of ADR 0371, which already contains the
  shared `verify_service_health` task include and a broad role migration
- close the remaining legacy verifier wrappers that still use hand-written
  `wait_for` and `uri` health checks instead of the shared helper
- validate the repo automation and verification gates from a fresh isolated
  worktree, then replay the governed service live-apply path for the affected
  services with explicit evidence captured in-branch
- update ADR 0371, this workstream, and the integrated mainline release/state
  surfaces once the latest realistic `origin/main` replay is fully verified

## Planned Verification

- `python3 scripts/workstream_registry.py --write`
- `python3 scripts/sync_plane_agent_issues.py --workstream ws-0371-live-apply`
- focused verifier tests and targeted repo-validation commands
- governed live-apply replays for the affected services from this exact-main
  worktree with end-to-end health verification and receipts
- final handoff notes describing what is complete on-branch and what still waits
  for merge-to-`main`

## Integrated Closeout Notes

- The final closeout now includes the protected mainline integration surfaces:
  `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml`.
- The shard-backed workstream registry moved this workstream to
  `workstreams/archive/2026/ws-0371-live-apply.yaml`; `workstreams.yaml`
  should be regenerated from that archived shard before merge.
- The exact-main live-apply evidence remains the authoritative proof of the
  platform change, while the integrated receipts and generated status pages
  describe the merged `0.178.143` repo and platform state.

## 2026-04-11 Progress

- Closed the remaining hand-written verifier wrappers in
  `librechat_runtime/tasks/verify.yml`,
  `litellm_runtime/tasks/verify.yml`, and
  `repowise_runtime/tasks/verify.yml` by switching them to the shared
  `lv3.platform.common` `verify_service_health` include.
- Added stable service live-apply wrappers for `librechat`, `litellm`, and
  `repowise` under `playbooks/services/` and aligned the `repowise`
  deployment surface in `config/service-capability-catalog.json`.
- Repaired repo automation on this branch so the remaining fresh-worktree
  generators no longer crash on Python's stdlib `platform` module shadowing
  the repo's `platform/` package. The rebased branch patches:
  `scripts/generate_ops_portal.py`,
  `scripts/platform_manifest.py`,
  `scripts/generate_status_docs.py`, and
  `scripts/generate_diagrams.py`.
- Updated `config/health-probe-catalog.json` so `librechat` and `neko` use the
  current nested `uptime_kuma.monitor` contract required by
  `scripts/uptime_contract.py`.

## 2026-04-13 Latest Origin/Main Replay

- Re-fetched `origin/main` and re-ran the governed service replays from the
  latest reachable tip `07ddfe99a`, which still carried repo version
  `0.178.127` and platform version `0.178.126`.
- `repowise` replayed successfully from
  `receipts/live-applies/evidence/2026-04-13-ws-0371-mainline-repowise-live-apply-r6-allow-in-place.txt`;
  direct follow-up verification on `docker-runtime` returned `status=ok` from
  `http://127.0.0.1:7070/health`, and the authenticated search path returned
  indexed matches.
- The first `litellm` exact-main replay failed closed in governed post-verify
  because `config/service-capability-catalog.json` lacked
  `health_probe_id: litellm` and `config/health-probe-catalog.json` had no
  `litellm` or `librechat` probe contracts. This branch now adds both catalog
  entries, after which the rerun in
  `receipts/live-applies/evidence/2026-04-13-ws-0371-mainline-litellm-live-apply-r2-success-attempt.txt`
  completed successfully.
- `litellm` also passed explicit follow-up checks after the governed replay:
  local `curl http://127.0.0.1:4000/health/liveliness` returned `I'm alive!`
  and an authenticated `GET /v1/models` returned the expected model catalog.
- `librechat` completed successfully in
  `receipts/live-applies/evidence/2026-04-13-ws-0371-mainline-librechat-live-apply.txt`,
  including the shared edge publication tail. External verification from the
  controller returned `HTTP 200` and HTML content for `https://chat.example.com/`.
- Both the successful `litellm` and `librechat` replays ended with the bounded
  Restic post-apply warning introduced on this branch: the live apply itself
  completed, and the final wrapper returned a tolerated `returncode: 124` after
  the 180-second trigger timeout instead of hanging indefinitely.

## Validation Completed

- `ansible-playbook -i inventory/hosts.yml playbooks/librechat.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/litellm.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/repowise.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/librechat.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/litellm.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/repowise.yml --syntax-check`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_service_live_apply_wrappers.py`
- `./scripts/validate_repo.sh workstream-surfaces`
- `./scripts/validate_repo.sh health-probes`
- `python3 scripts/uptime_contract.py --write`
- `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`
- `git diff --check`
- `uv run pytest tests/test_uptime_contract.py tests/test_service_live_apply_wrappers.py tests/test_changedetection_metadata.py tests/test_paperless_metadata.py tests/test_crawl4ai_metadata.py` returned `13 passed`
- `./scripts/validate_repo.sh health-probes generated-docs agent-standards`
- `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 python -m pytest -q tests/test_validation_toolkit.py tests/test_subdomain_catalog.py tests/test_validate_service_catalog.py tests/test_validate_portal_auth.py tests/test_ops_portal.py tests/test_common_docker_bridge_chains_helper.py tests/test_litellm_runtime_role.py tests/test_repowise_playbook.py tests/test_service_compose_macro_resolution.py tests/test_service_live_apply_wrappers.py tests/test_ollama_runtime_role.py tests/test_rag_context_playbook.py tests/test_rag_context_runtime_role.py -k 'not test_role_requires_platform_context_minio_secret_before_runtime_render'` returned `76 passed, 1 deselected`
- `uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check`

## Governed Path Findings

- `make live-apply-service service=librechat env=production` originally failed
  in preflight because `config/workflow-catalog.json` referenced local receipt
  scaffolds that did not exist in a fresh worktree. Those ignored local receipt
  paths were materialized so the governed path could progress.
- The original fresh-worktree blockers were closed on this branch:
  - `generate_ops_portal.py --check` now passes after placeholder-domain
    substitution and reconciliation validation were made worktree-safe
  - `ws-0377-repo-intake-subdomain` now carries ADR `0224` in both
    `workstreams.yaml` and `workstreams/active/ws-0377-repo-intake-subdomain.yaml`

## Live-Apply Outcome

- The first scoped `litellm` replay on `2026-04-11` hit a real
  `proxmox_network` reachability failure after `ifreload` on `proxmox-host`;
  that outage is intentionally preserved in the early `r1` evidence.
- After the generator and catalog fixes landed and the host was reachable
  again, the branch-local scoped runner replays completed successfully:
  - `receipts/live-applies/evidence/2026-04-12-ws0371-litellm-live-apply-r1.txt`
    finished with `docker-runtime ok=114 changed=5 failed=0 rescued=1`,
    `postgres ok=28 changed=0 failed=0`, and
    `proxmox-host ok=24 changed=5 failed=0`
  - `receipts/live-applies/evidence/2026-04-12-ws0371-librechat-live-apply-r1.txt`
    finished with `coolify ok=102 changed=3 failed=0`,
    `nginx ok=48 changed=4 failed=0`, and
    `proxmox-host ok=389 changed=0 failed=0`
  - `receipts/live-applies/evidence/2026-04-12-ws0371-repowise-live-apply-r7.txt`
    finished with `docker-runtime ok=47 changed=5 failed=0`
- The branch also recovered a real downstream regression exposed during the
  replay sequence:
  - `rag-context` required the platform-context service-topology, compose
    macro, and `validation_toolkit.py` sync fixes before its scoped recovery
    succeeded; the final green replay is preserved in
    `receipts/live-applies/evidence/2026-04-12-ws0371-rag-context-recovery-r7.txt`
  - the follow-up Postgres reconcile for Windmill completed successfully in
    `receipts/live-applies/evidence/2026-04-12-ws0371-windmill-postgres-reconcile-r2.txt`
  - `repowise` needed a final compose publish fix because Docker only kept the
    loopback `127.0.0.1:7070` binding; the template now publishes a single
    host-facing bind so the shared NGINX edge can reach `10.10.10.20:7070`
- The later exact-main replay on `2026-04-13` reconfirmed the current
  production state from `origin/main@07ddfe99a` and surfaced one remaining
  governed-wrapper contract gap:
  - `litellm` first failed closed in the wrapper because the service catalog
    and health probe catalog were missing `litellm`/`librechat` mappings; the
    failing transcript is preserved in
    `receipts/live-applies/evidence/2026-04-13-ws-0371-mainline-litellm-live-apply-r1-missing-health-probe.txt`
  - after adding the missing catalog contracts, `repowise`, `litellm`, and
    `librechat` all passed their governed exact-main replays on the same tip
  - the only residual warning in the successful replays is the intentional
    bounded Restic timeout after 180 seconds

## Direct Verification

- `receipts/live-applies/evidence/2026-04-12-ws0371-end-to-end-verification-r1.txt`
  confirms the final post-replay state:
  - `docker-runtime` local probes returned healthy responses for `litellm`,
    `repowise`, and `platform-context`
  - `coolify` returned `librechat-root ok` and `librechat-health OK`
  - `nginx` reached both upstreams directly:
    `http://10.10.10.20:7070/health` and `http://10.10.10.70:8096/health`
  - `chat.example.com/` returned `HTTP 200`
  - `repowise.example.com/health` returned `HTTP 200` with the Repowise JSON
    health payload
- The latest exact-main rerun on `2026-04-13` added controller-side
  verification against the current production surfaces:
  - `https://chat.example.com/` returned `HTTP 200` and the LibreChat HTML shell
  - `docker-runtime` returned `{"status":"ok","collection":"repowise",...}`
    from `http://127.0.0.1:7070/health`
  - authenticated LiteLLM `GET http://127.0.0.1:4000/v1/models` returned the
    expected model list after the governed replay

## 2026-04-14 Exact-Main Closeout

- Re-fetched `origin/main` to the latest realistic base
  `7b72694975ef8aae83e59d96c08dd27181595b2e` and replayed all remaining
  ADR 0371 services from that exact-main candidate.
- `repowise` converged successfully on `docker-runtime`; the container reported
  healthy locally, `http://127.0.0.1:7070/health` returned the Repowise JSON
  payload, and the public edge stabilized to `HTTP 200` on
  `https://repowise.example.com/health`.
- `litellm` completed the full governed replay across `proxmox-host`,
  `postgres`, and `docker-runtime`, including the Proxmox guest-firewall
  refresh for `docker-runtime`; direct verification returned `HTTP 200` with
  `"I'm alive!"` from `http://10.10.10.20:4000/health/liveliness`.
- `librechat` completed the full governed replay across `proxmox-host`,
  `coolify`, and `nginx`, and the public surface now returns `HTTP 200` on
  `https://chat.example.com/`.

## Final Verification

- The large focused pytest slice passed on the latest merged exact-main tree:
  `250 passed in 39.66s`.
- The direct repo gate bundle
  `./scripts/validate_repo.sh agent-standards data-models health-probes`
  passed on the integrated candidate.
- `repowise`, `litellm`, and `librechat` exact-main replay evidence is recorded
  under `receipts/live-applies/evidence/2026-04-14-ws-0371-mainline-*.txt`,
  with controller-side direct verification collected separately in
  `receipts/live-applies/evidence/2026-04-14-ws-0371-mainline-direct-verification-r1-0.178.142.txt`.
- The final integration gates also record live-apply receipt schema validation,
  whitespace diff checks, build-server reachability, and remote validation
  evidence under the matching `2026-04-14-ws-0371-mainline-final-*.txt`
  transcripts.

## Promotion Gate Outcome

- The first `git push origin HEAD:refs/heads/main` attempt from the detached
  ship worktree hit the remote build-server fallback path and then failed in
  local fallback for three reasons that were not release-tree regressions:
  - the detached ship worktree did not have the ignored generated
    `config/generated/*` and `inventory/group_vars/platform_hairpin.yml`
    surfaces present, so `data-models` and `alert-rules` observed stale local
    generation state that did not reproduce in the feature worktree
  - the local `integration-tests` fallback was pointing at raw `pytest tests/`
    instead of the governed `scripts/integration_suite.py` wrapper
  - the remaining full-repo `ansible-lint` failures were all in untouched
    baseline files outside the ADR 0371 change set
- The final branch now includes the local fallback fix for
  `config/validation-gate.json` plus the shared verify-task lint cleanup, and
  the focused substitute validations all pass from the feature worktree:
  - `./scripts/validate_repo.sh data-models`
  - `./scripts/validate_repo.sh alert-rules`
  - `./scripts/run_python_with_packages.sh pytest -- scripts/integration_suite.py --mode gate --environment staging --report-file .local/integration-tests/gate-last-run.json`
  - `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 python -m pytest -q tests/test_service_live_apply_wrappers.py tests/test_validation_gate.py`
- Because the remaining full primary-branch gate failure reduced to the
  untouched whole-repo `ansible-lint` baseline, the final `origin/main`
  promotion uses the governed `skip_remote_gate` waiver recorded in the
  receipt above instead of `--no-verify`.

## Integration Notes

- The first April 11 scoped `litellm` replay preserved the historical
  `ifreload`/SSH failure on `proxmox-host`; the 2026-04-14 exact-main replay
  no longer reproduced it because the host network render was already converged
  and the reload path was skipped cleanly.
- The `repowise` public edge briefly returned `502` during startup while the
  backend was still stabilizing. The direct post-replay checks captured the
  steady-state `HTTP 200` health response once the service finished starting.
- The final exact-main shell wrappers completed their governed replays, but the
  optional controller-side footer probes stalled after the play recap. Direct
  verification was rerun immediately and recorded separately so the branch
  keeps a clean audit trail for the verified production state.
