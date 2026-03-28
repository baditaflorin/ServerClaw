# Workstream ws-0194-main-merge

- ADR: [ADR 0194](../adr/0194-coolify-paas-deploy-from-repo.md)
- Title: Integrate ADR 0194 live apply into `origin/main`
- Status: merged
- Branch: `codex/ws-0194-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0194-main-merge`
- Owner: codex
- Depends On: `ws-0194-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0194 Coolify live-apply branch into the latest `origin/main`, refresh the protected integration files, replay the live apply from the merged candidate, and push the final mainline state only after the governed repo-deploy path is re-verified end to end.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0194-main-merge.md`
- `README.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `docs/adr/0194-coolify-paas-deploy-from-repo.md`
- `docs/workstreams/adr-0194-coolify-paas-deploy-from-repo.md`
- `docs/runbooks/configure-coolify.md`
- `receipts/live-applies/2026-03-28-adr-0194-coolify-paas-deploy-from-repo-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0194-coolify-paas-deploy-from-repo-mainline-live-apply.json`
- `build/platform-manifest.json`

## Plan

- refresh the ADR 0194 integration on top of the latest `origin/main`
- replay `make converge-coolify` from the merged candidate
- re-run the governed `deploy-repo` smoke path and edge verification
- record the canonical mainline live-apply receipt and push the final merge into `origin/main`

## Result

- Merged-main replay completed from commit `093af353` with `coolify-lv3 ok=115 changed=7 failed=0`, `nginx-lv3 ok=71 changed=5 failed=0`, and `proxmox_florin ok=43 changed=5 failed=0`.
- Governed verification succeeded end to end: `python3 scripts/coolify_tool.py whoami`, a fresh `deploy-repo` smoke deployment with deployment `klmsg3ybgvp7xwnk8op3cdlp`, and direct edge probes for `coolify.lv3.org`, `repo-smoke.apps.lv3.org`, and `apps.lv3.org`.
- Mainline validation gates passed after the final evidence refresh, including the focused `98 passed in 2.45s` pytest slice, agent-standards validation, repository data-model validation, generated artifact checks, and `git diff --check`.
