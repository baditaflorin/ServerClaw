# Workstream ws-0297-live-apply: Live Apply ADR 0297 From Latest `origin/main`

- ADR: [ADR 0297](../adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md)
- Title: Deploy the repo-managed Renovate proposal path through Gitea Actions, OpenBao, and Harbor
- Status: in_progress
- Branch: `codex/ws-0297-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0297-live-apply`
- Owner: codex
- Depends On: `adr-0068`, `adr-0077`, `adr-0083`, `adr-0087`, `adr-0119`, `adr-0143`, `adr-0229`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0297`, `docs/workstreams/ws-0297-live-apply.md`, `docs/runbooks/configure-gitea.md`, `docs/runbooks/configure-openbao.md`, `docs/runbooks/configure-renovate.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `.gitea/workflows/renovate.yml`, `.gitea/workflows/release-bundle.yml`, `renovate.json`, `scripts/validate_repo.sh`, `scripts/validate_renovate_contract.py`, `scripts/renovate_runtime_token.py`, `scripts/renovate_stack_digest_guard.py`, `collections/ansible_collections/lv3/platform/roles/common/`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `collections/ansible_collections/lv3/platform/roles/gitea_runner/`, `tests/`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add a root `renovate.json` contract that manages the currently supported stack image and version surfaces
- run Renovate as a scheduled/manual Gitea Actions workflow on `docker-build-lv3`
- deliver the Renovate bootstrap credential through OpenBao onto the runner host and mint a short-lived scoped Gitea token at workflow runtime
- pull the Renovate runtime image through Harbor and pin it to a digest in the workflow
- verify the live path end to end, including repo validation and workflow execution from the latest synchronized `origin/main` base

## Non-Goals

- updating protected release files on this workstream branch before an exact-main integration step
- widening Gitea or OpenBao publication beyond the current private-only control-plane model
- granting Renovate autonomous deploy or merge permissions

## Expected Repo Surfaces

- `docs/adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md`
- `docs/workstreams/ws-0297-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/configure-openbao.md`
- `docs/runbooks/configure-renovate.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `.gitea/workflows/renovate.yml`
- `.gitea/workflows/release-bundle.yml`
- `renovate.json`
- `scripts/validate_repo.sh`
- `scripts/validate_renovate_contract.py`
- `scripts/renovate_runtime_token.py`
- `scripts/renovate_stack_digest_guard.py`
- `scripts/generate_platform_vars.py`
- `.ansible-lint-ignore`
- `config/ansible-role-idempotency.yml`
- `collections/ansible_collections/lv3/platform/roles/common/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/`
- `collections/ansible_collections/lv3/platform/roles/openbao_postgres_backend/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runner/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`
- `collections/ansible_collections/lv3/platform/roles/postgres_vm/`
- `tests/`
- `tests/test_docker_runtime_role.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_mail_platform_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_openbao_postgres_backend_role.py`
- `tests/test_postgres_vm_role.py`
- `receipts/live-applies/`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` publishes the private OpenBao HTTP listener on its guest IP only for `docker-build-lv3`
- `docker-runtime-lv3` runs the managed Gitea stack with a repo-managed `renovate-bot` identity
- `docker-build-lv3` runs the managed Gitea runner with a mounted OpenBao-rendered Renovate bootstrap env file
- a manual or scheduled Gitea Actions run executes Renovate successfully from the Harbor-pinned image using a short-lived token minted at job runtime

## Current Branch State

- the repo-managed Renovate config, workflow, token helper, and validation hooks are implemented on this branch
- the Gitea/OpenBao/runner plumbing is now live on the current platform: `make converge-openbao` succeeded after publishing the private OpenBao HTTP listener on `10.10.10.20:8201`, and `make converge-gitea` then completed successfully with the Renovate bot account plus runner credential bundle in place
- the live replay uncovered and repaired shared dependency drift outside the narrow ADR 0297 surface: Docker worktree path handling, PostgreSQL reserved connection budgeting, Keycloak realm-object retries, mail-platform stale-network recovery, and OpenBao credential helper recovery now match the settled live estate on this branch
- branch-local evidence already proves the runner host renders `/opt/gitea-runner/credentials/renovate/renovate.env`, the runner container sees `/var/run/lv3/renovate/renovate.env`, and the Gitea admin API returns an active `renovate-bot` identity
- the remaining end-to-end proof is on the repository boundary, not the runtime plumbing: the private Gitea repo `ops/proxmox_florin_server` is a separate internal snapshot on commit `9f988bf58f6f02c4add3c6292c65fbed929edac9`, so the branch still needs a governed private Gitea push plus a Renovate workflow dispatch before the workflow itself can be recorded as verified

## Pending Verification

- refresh this worktree onto the latest `origin/main`, rerun the repo validation contract from the settled branch state, and preserve the outputs in branch-local receipts
- publish the integrated source commit into the private Gitea repo so `.gitea/workflows/renovate.yml` exists in the live internal snapshot
- dispatch the Renovate workflow against the pushed Gitea ref, verify the short-lived token mint / cleanup path and runner-backed Renovate container execution, and preserve the run plus dashboard or PR evidence in receipts
- update ADR 0297 metadata, the ADR index, and the workstream registry with the final implemented and live-applied facts once the branch-local and exact-main proofs are both complete
