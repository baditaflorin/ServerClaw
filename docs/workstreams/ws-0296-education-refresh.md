# Workstream WS-0296: Education Repo Refresh And Named Deploy Profiles

- ADR: [ADR 0194](../adr/0194-coolify-paas-deploy-from-repo.md), [ADR 0224](../adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md), [ADR 0274](../adr/0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments.md)
- Title: Pull the latest `education_wemeshup` release through the governed Coolify lane and codify the repeatable operator path as a named profile
- Status: merged
- Implemented In Repo Version: `0.177.89`
- Live Applied In Platform Version: `0.130.59`
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0296-education-refresh`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0296-education-refresh`
- Owner: codex
- Depends On: `adr-0194-coolify-paas-deploy-from-repo`, `adr-0224-self-service-repo-intake-and-agent-assisted-deployments`, `adr-0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0296-education-refresh.md`, `docs/runbooks/configure-coolify.md`, `config/repo-deploy-catalog.json`, `docs/schema/repo-deploy-catalog.schema.json`, `scripts/repo_deploy_profiles.py`, `scripts/lv3_cli.py`, `scripts/validate_repository_data_models.py`, `Makefile`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/correction-loops.json`, `tests/test_lv3_cli.py`, `tests/test_repo_deploy_profiles.py`, `receipts/live-applies/2026-03-30-adr-0224-education-repo-profile-refresh-live-apply.json`

## Scope

- verify the latest upstream `education_wemeshup` `main` revision before deployment
- codify the governed operator path as a named repo-deploy profile instead of retyping raw Coolify arguments
- use the named profile to refresh production and verify the public taxonomy still serves more than 1000 activities
- record the live apply and carry the governed refresh path onto mainline truth

## Non-Goals

- building a second deployment engine outside the existing Coolify lane
- redesigning the future browser intake surface beyond the existing ADR 0224 direction
- changing protected release files before a dedicated mainline integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0296-education-refresh.md`
- `docs/runbooks/configure-coolify.md`
- `config/repo-deploy-catalog.json`
- `docs/schema/repo-deploy-catalog.schema.json`
- `scripts/repo_deploy_profiles.py`
- `scripts/lv3_cli.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/correction-loops.json`
- `tests/test_lv3_cli.py`
- `tests/test_repo_deploy_profiles.py`
- `receipts/live-applies/2026-03-30-adr-0224-education-repo-profile-refresh-live-apply.json`

## Expected Live Surfaces

- `education-wemeshup.apps.lv3.org`
- one fresh live-apply receipt for the named profile-driven redeploy

## Verification Plan

- validate the repo-deploy catalog and the focused Coolify CLI/tests from this worktree
- confirm the upstream GitHub `main` head before triggering the redeploy
- deploy production through the named profile path instead of raw Coolify arguments
- verify the public taxonomy endpoint returns more than 1000 activities after the refresh

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_lv3_cli.py tests/test_repo_deploy_profiles.py -q` passed with `55 passed in 2.91s`.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` returned `Repository data models OK`, and `./scripts/validate_repo.sh agent-standards` passed from this worktree.
- `git ls-remote git@github.com:baditaflorin/education_wemeshup.git HEAD refs/heads/main` confirmed upstream `main` at `4d27ded77559269d1a5e05b3e3aaf9acd198a0ea` before the redeploy.
- `make deploy-repo-profile PROFILE=education-wemeshup-production DEPLOY_PROFILE_ARGS='--dry-run --wait'` expanded the catalog entry into the governed Coolify wrapper, and `make coolify-manage ACTION=whoami` confirmed the private controller path and usable deployment server.
- `make deploy-repo-profile PROFILE=education-wemeshup-production DEPLOY_PROFILE_ARGS='--wait --timeout 1800'` finished on attempt `1` with deployment `lwyww144yknn3fe524ou8pq7`.
- Public verification after the refresh returned `HTTP/2 200` for `https://education-wemeshup.apps.lv3.org/`, and `/api/v1/catalog/taxonomy` returned `catalogVersion: 2.0.0`, `activityCount: 1056`, and `categoryCount: 95`.

## Notes For The Next Assistant

- The current better operator path should become `python3 scripts/lv3_cli.py deploy-repo-profile education-wemeshup-production --wait` or the equivalent `make deploy-repo-profile PROFILE=education-wemeshup-production DEPLOY_PROFILE_ARGS='--wait'`.
- The existing generic `deploy-repo` path remains the underlying contract and should still work for one-off repos.
