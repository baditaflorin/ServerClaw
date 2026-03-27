# Workstream WS-0195: Renovate Live Apply

- ADR: [ADR 0195](../adr/0195-renovate-automated-dependency-prs.md)
- Title: Live apply and end-to-end verification for the internal Gitea Renovate workflow
- Status: ready
- Branch: `codex/ws-0195-live-apply`
- Worktree: `.worktrees/ws-0195-live-apply`
- Owner: codex
- Depends On: `adr-0143-gitea`, `adr-0168-idempotency-ci`
- Conflicts With: none
- Shared Surfaces: `config/renovate.json`, `.gitea/workflows/renovate.yml`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `scripts/publish_gitea_repo.py`, `docs/runbooks/configure-gitea.md`, `docs/runbooks/configure-renovate.md`, `workstreams.yaml`

## Scope

- add a repo-managed Renovate configuration and gate validation surface
- extend the Gitea converge path so the internal repository gets a dedicated Renovate token and Actions secret
- add an explicit publish path that seeds or refreshes the internal Gitea repository from the current checkout
- replay the Gitea converge and verify the Renovate workflow path end to end on the live platform

## Non-Goals

- merge this branch to GitHub `main`
- bump `VERSION`, update release sections in `changelog.md`, or rewrite the top-level README integrated summary
- implement Harbor or Plane enrichments that depend on ADR 0193 or ADR 0201 landing first

## Expected Repo Surfaces

- `config/renovate.json`
- `docs/schema/renovate-config.schema.json`
- `.gitea/workflows/renovate.yml`
- `scripts/renovate_config.py`
- `scripts/publish_gitea_repo.py`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `tests/test_renovate_config.py`
- `tests/test_gitea_runtime_role.py`

## Expected Live Surfaces

- internal Gitea repository secret `RENOVATE_TOKEN`
- mirrored controller-local token artifact under `.local/gitea/renovate-token.txt`
- `ops/proxmox_florin_server` populated in internal Gitea with the Renovate workflow on the selected branch or mainline ref
- a verified Gitea Actions Renovate run on `docker-build-lv3`

## Verification

- pending

## Merge Criteria

- repository validation passes with the new Renovate config in the data-model gate
- `make converge-gitea` replays cleanly from this worktree
- the internal Gitea repository is populated and the Renovate workflow runs successfully
- a live-apply receipt records the evidence and any merge-to-main follow-up

## Notes For The Next Assistant

- the internal Gitea repository was discovered to be bootstrapped but still effectively empty before this workstream began
- the live apply should verify both the token/bootstrap path and the repo publish path, otherwise the daily workflow is not actually reachable
