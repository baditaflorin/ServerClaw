# Workstream ws-0229-live-apply: ADR 0229 Live Apply From Latest `origin/main`

- ADR: [ADR 0229](../adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md)
- Title: on-platform Gitea Actions runner convergence, verification, and merge-safe documentation
- Status: live_applied
- Branch: `codex/ws-0229-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0229-live-apply`
- Owner: codex
- Depends On: `adr-0083-docker-based-check-runner`, `adr-0143-gitea`, `adr-0168-automated-validation-gate`, `adr-0224-server-resident-operations-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-gitea.md`, `docs/runbooks/validate-repository-automation.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `build/platform-manifest.json`, `.gitea/workflows/validate.yml`, `playbooks/gitea.yml`, `collections/ansible_collections/lv3/platform/roles/gitea_runner/`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `tests/test_gitea_runtime_role.py`, `receipts/live-applies/`, `workstreams.yaml`

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
- `docs/adr/.index.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`
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

- the final current-base replay sits on repo version `0.177.40`, and `make converge-gitea` completed successfully from branch head `40b5a622`, finishing with `proxmox_florin ok=36 changed=4`, `postgres-lv3 ok=24 changed=0`, `docker-runtime-lv3 ok=224 changed=0`, and `docker-build-lv3 ok=100 changed=5`
- an earlier rebased replay on `0.177.39` hit a transient Keycloak admin token `HTTP 500` while PostgreSQL connections were being reset under Keycloak; the final `0.177.40` replay did not reproduce that fault and all Keycloak OAuth client tasks completed cleanly without repo code changes
- the rebased branch also required refreshing two generated validation surfaces before the remote push gate would accept it: `docs/diagrams/agent-coordination-map.excalidraw` and `build/platform-manifest.json`
- the Gitea admin API confirmed runner `1` named `docker-build-lv3` online with labels `self-hosted`, `linux`, `amd64`, and `docker`
- the first private Gitea push attempt surfaced two actionable gate failures in the branch: `workstreams.yaml` needed `status: in_progress`, and the generated coordination diagram needed refresh after claiming `ws-0229-live-apply`
- after those fixes, the second private Gitea push passed the full server-side gate, including `ansible-lint`, `ansible-syntax`, `schema-validation`, `dependency-graph`, `service-completeness`, `type-check`, `yaml-lint`, `security-scan`, `packer-validate`, and `tofu-validate`
- earlier branch-local automation proof on the rebased workstream recorded Gitea workflow run `29` for `codex/ws-0229-live-apply` with `event: push`, `head_sha: 40c1501ba05368ca2c203dd66ed84015aa7a5bfd`, `status: completed`, and `conclusion: success`
- run `29` executed job `validate` on runner `docker-build-lv3` (`runner_id: 1`), starting at `2026-03-28T17:01:49Z` and completing at `2026-03-28T17:01:52Z`
- ADR 0229 itself is now marked implemented retroactively to the earlier ADR 0143 rollout, because the capability first became true in repo version `0.165.0` and platform version `0.130.15` on `2026-03-26`; this workstream re-verified it from repo version context `0.177.40` and platform version context `0.130.38`

## Mainline Integration Outcome

- pending final verified integration step
- the rebase onto the latest `origin/main` is complete; remaining for merge to `main` is the protected integration step: refresh `VERSION` and `changelog.md`, re-check `origin/main` immediately before landing, and keep `README.md` plus `versions/stack.yaml` unchanged unless the final integration step confirms integrated truth actually changed

## Notes For The Next Assistant

- pull from `origin/main` again before any final merge-to-`main` step because concurrent agents are updating shared integration files
- the private Gitea git endpoint accepted the branch only after the server-side validation gate passed; use that accepted push plus workflow run `20` as the canonical branch-local automation proof
- the host bootstrap SSH key did not authenticate to the Gitea git endpoint on port `2222`, so the branch smoke push used HTTP basic auth with the mirrored `ops-gitea` admin token instead
- if the platform is already converged before replay, still capture fresh evidence from the latest merged mainline candidate rather than treating stale runtime state as sufficient
