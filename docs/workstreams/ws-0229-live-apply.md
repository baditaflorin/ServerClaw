# Workstream ws-0229-live-apply: ADR 0229 Live Apply From Latest `origin/main`

- ADR: [ADR 0229](../adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md)
- Title: on-platform Gitea Actions runner convergence, verification, and merge-safe documentation
- Status: in-progress
- Branch: `codex/ws-0229-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0229-live-apply`
- Owner: codex
- Depends On: `adr-0083-docker-based-check-runner`, `adr-0143-gitea`, `adr-0168-automated-validation-gate`, `adr-0224-server-resident-operations-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md`, `docs/runbooks/configure-gitea.md`, `.gitea/workflows/validate.yml`, `playbooks/gitea.yml`, `collections/ansible_collections/lv3/platform/roles/gitea_runner/`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `tests/test_gitea_runtime_role.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- replay the merged `origin/main` Gitea and runner automation from an isolated worktree
- verify that the dedicated `docker-build-lv3` runner is registered, online, and able to execute the repo-managed validation workflow
- confirm the focused repository validation and automation paths still pass from the latest mainline candidate
- update ADR-local, runbook-local, receipt, and workstream state so another agent can merge safely if protected integration files must wait

## Non-Goals

- changing protected release files before the final verified mainline integration step
- widening Gitea publication beyond the current private access model
- granting autonomous production mutation to Actions jobs without a separate governed path

## Expected Repo Surfaces

- `docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md`
- `docs/workstreams/ws-0229-live-apply.md`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/validate-repository-automation.md`
- `.gitea/workflows/validate.yml`
- `playbooks/gitea.yml`
- `collections/ansible_collections/lv3/platform/roles/gitea_runner/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `scripts/validate_repo.sh`
- `tests/test_gitea_runtime_role.py`
- `receipts/live-applies/`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-build-lv3` is present in Gitea as an online self-hosted runner with the repo-managed labels
- a fresh push from this branch triggers `.gitea/workflows/validate.yml` on the platform runner
- the workflow completes successfully using the server-resident runner path instead of laptop-local execution

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_gitea_runtime_role.py`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-gitea`
- `curl -sf http://100.64.0.1:3009/user/login >/dev/null`
- authenticated Gitea API verification for runner registration and recent workflow runs
- branch push to the private Gitea remote that produces a successful `validate` workflow run on `codex/ws-0229-live-apply`

## Merge Criteria

- the merged-main Gitea playbook converges cleanly from this worktree
- the runner registration, runtime container, and workflow execution all verify end to end
- the branch records live-apply evidence, ADR metadata, and workstream status clearly enough for a safe merge or direct mainline integration

## Live Apply Outcome

- in progress

## Mainline Integration Outcome

- pending final verified integration step

## Notes For The Next Assistant

- pull from `origin/main` again before any final merge-to-`main` step because concurrent agents are updating shared integration files
- if the platform is already converged before replay, still capture fresh evidence from the latest merged mainline candidate rather than treating stale runtime state as sufficient
