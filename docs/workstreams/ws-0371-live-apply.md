# Workstream ws-0371-live-apply: ADR 0371 Parameterized Service Verification Tasks

- ADR: [ADR 0371](../adr/0371-parameterized-verify-tasks.md)
- Title: re-verify parameterized service verification tasks from latest origin/main
- Status: ready
- Included In Repo Version: pending merge to `main`
- Branch-Local Receipt: successful scoped replays for `litellm`, `librechat`, `repowise`, plus `rag-context` recovery and end-to-end verification evidence
- Mainline Receipt: pending
- Implemented On: 2026-04-12
- Live Applied On: 2026-04-12
- Live Applied In Platform Version: pending
- Latest Verified Base: `origin/main@b2a4e2315` (`repo 0.178.123`, `platform 0.178.77`)
- Branch: `codex/ws-0371-live-apply`
- Worktree: `.worktrees/ws-0371-live-apply`
- Owner: codex
- Depends On: `ADR 0165`, `ADR 0289`, `ADR 0371`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health_extra.yml`, `collections/ansible_collections/lv3/platform/roles/librechat_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/litellm_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/repowise_runtime/tasks/verify.yml`, `config/health-probe-catalog.json`, `config/service-capability-catalog.json`, `docs/adr/0371-parameterized-verify-tasks.md`, `docs/runbooks/live-apply-receipts-and-verification-evidence.md`, `playbooks/services/librechat.yml`, `playbooks/services/litellm.yml`, `playbooks/services/repowise.yml`, `platform/ansible/execution_scopes.py`, `receipts/live-applies/*adr-0371*`, `receipts/live-applies/evidence/*ws-0371*`, `scripts/generate_diagrams.py`, `scripts/generate_ops_portal.py`, `scripts/generate_status_docs.py`, `scripts/platform_manifest.py`, `tests/test_ansible_execution_scopes.py`, `tests/test_service_live_apply_wrappers.py`, `workstreams/active/ws-0371-live-apply.yaml`, `workstreams.yaml`

## Scope

- confirm the latest `origin/main` state of ADR 0371, which already contains the
  shared `verify_service_health` task include and a broad role migration
- close the remaining legacy verifier wrappers that still use hand-written
  `wait_for` and `uri` health checks instead of the shared helper
- validate the repo automation and verification gates from a fresh isolated
  worktree, then replay the governed service live-apply path for the affected
  services with explicit evidence captured in-branch
- update ADR 0371 and this workstream with the verified implementation/live
  status while leaving protected mainline release files for the merge step

## Planned Verification

- `python3 scripts/workstream_registry.py --write`
- `python3 scripts/sync_plane_agent_issues.py --workstream ws-0371-live-apply`
- focused verifier tests and targeted repo-validation commands
- governed live-apply replays for the affected services from this exact-main
  worktree with end-to-end health verification and receipts
- final handoff notes describing what is complete on-branch and what still waits
  for merge-to-`main`

## Merge Notes

- Do not bump `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml`
  on this branch.
- If the branch proves ADR 0371 live-applied successfully, update only the
  ADR-local/workstream-local state here and leave shared integration truth for
  the final mainline step.

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
- `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`
- `git diff --check`
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

## Direct Verification

- `receipts/live-applies/evidence/2026-04-12-ws0371-end-to-end-verification-r1.txt`
  confirms the final post-replay state:
  - `docker-runtime` local probes returned healthy responses for `litellm`,
    `repowise`, and `platform-context`
  - `coolify` returned `librechat-root ok` and `librechat-health OK`
  - `nginx` reached both upstreams directly:
    `http://10.10.10.20:7070/health` and `http://10.10.10.70:8096/health`
  - `chat.lv3.org/` returned `HTTP 200`
  - `repowise.lv3.org/health` returned `HTTP 200` with the Repowise JSON
    health payload

## Remaining Mainline Integration Work

- Rebase this workstream onto the current `origin/main` tip before cutting the
  protected release and canonical-truth surfaces.
- Run the final exact-main validation and generation bundle from the rebased
  tree, including the generated SLO/canonical-truth surfaces that intentionally
  wait for the integration step.
- Cut the new repo release on `main`, update `versions/stack.yaml` with the
  merged exact-main truth, and replay the exact-main verification path so the
  first canonical platform version for ADR 0371 is recorded on `main`.
