# Workstream ws-0371-live-apply: ADR 0371 Parameterized Service Verification Tasks

- ADR: [ADR 0371](../adr/0371-parameterized-verify-tasks.md)
- Title: re-verify parameterized service verification tasks from latest origin/main
- Status: in_progress
- Included In Repo Version: pending merge to `main`
- Branch-Local Receipt: pending
- Mainline Receipt: pending
- Implemented On: pending
- Live Applied On: pending
- Live Applied In Platform Version: pending
- Latest Verified Base: `origin/main@86390fcc8` (`repo 0.178.116`, `platform 0.178.77`)
- Branch: `codex/ws-0371-live-apply`
- Worktree: `.worktrees/ws-0371-live-apply`
- Owner: codex
- Depends On: `ADR 0165`, `ADR 0289`, `ADR 0371`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health_extra.yml`, `collections/ansible_collections/lv3/platform/roles/librechat_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/litellm_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/repowise_runtime/tasks/verify.yml`, `docs/adr/0371-parameterized-verify-tasks.md`, `docs/runbooks/live-apply-receipts-and-verification-evidence.md`, `workstreams/active/ws-0371-live-apply.yaml`, `workstreams.yaml`

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
