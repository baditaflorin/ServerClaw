# Workstream ws-0228-main-merge

- ADR: [ADR 0228](../adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- Title: Integrate ADR 0228 live apply into `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.71
- Platform Version Observed During Merge: 0.130.49
- Release Date: 2026-03-29
- Branch: `codex/ws-0228-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0228-main-merge`
- Owner: codex
- Depends On: `ws-0228-live-apply`
- Conflicts With: none
- Source Commit: `afb966493ff843c9f8f0a287248f51fe693a9ff5`
- Mainline Receipt: `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply`

## Purpose

Carry the verified ADR 0228 live-apply evidence onto the latest `origin/main`,
cut the protected release and canonical-truth files from that merged candidate,
replay the live Windmill convergence from the current mainline, and push the
fully integrated result to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0228-main-merge.md`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.71.md`
- `versions/stack.yaml`
- `README.md`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md`
- `docs/workstreams/ws-0228-live-apply.md`
- `docs/runbooks/windmill-default-operations-surface.md`
- `docs/runbooks/validation-gate.md`
- `docs/adr/.index.yaml`
- `scripts/generate_ops_portal.py`
- `tests/test_ops_portal.py`
- `receipts/live-applies/2026-03-28-adr-0228-windmill-default-operations-surface-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0228-mainline-converge-r25.txt`
- `receipts/live-applies/evidence/2026-03-29-adr-0228-mainline-worker-validation.txt`
- `receipts/live-applies/evidence/2026-03-29-adr-0228-mainline-windmill-proof.txt`
- `receipts/live-applies/evidence/2026-03-29-adr-0228-mainline-server-state.txt`

## Outcome

- `git fetch origin --prune` confirmed the integration worktree still contained the latest published `origin/main`, and the exact-main replay candidate for ADR 0228 was branch head `afb96649`
- commit `afb96649` fixed one last worker-only validation defect by making `scripts/generate_ops_portal.py` parse cleanly on Python `3.11`, with the empty-state coverage added in `tests/test_ops_portal.py`
- `make converge-windmill` replay `r25` then completed successfully from the merged worktree, including `Verify the Windmill default operations scripts are seeded` and `Assert the Windmill default operations scripts exist`, with final recap `docker-runtime ok=248 changed=50`, `postgres ok=64 changed=1`, and `proxmox-host ok=37 changed=4`
- the direct worker-local validation subset now passes from `/srv/proxmox-host_server`: `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules generated-docs generated-portals`
- the final repo-validation sweep passed for `agent-standards`, `generated-docs`, `generated-portals`, `live_apply_receipts.py --validate`, `platform_manifest.py --check`, `generate_status_docs.py --check`, `generate_diagrams.py --check`, `python3.11 -m py_compile scripts/generate_ops_portal.py`, `pytest tests/test_ops_portal.py -q`, and `git diff --check`
- the live Windmill proof bundle recorded `CE v1.662.0`, `9` healthy workers, a successful `windmill_healthcheck`, `weekly_capacity_report: ok`, `audit_token_inventory: attention_required` only because `local-platform-cli` expires on `2026-03-31`, dry-run `token_exposure_response: completed`, and overall `post_merge_gate: ok`
- the green `post_merge_gate` result currently depends on the intended worker-local fallback because the primary Docker-runner validation path still cannot pull `registry.example.com/check-runner/*` images on the worker and returns `502 Bad Gateway`
- `./scripts/validate_repo.sh workstream-surfaces` was also exercised and only hit the expected terminal-workstream guard for running from `codex/ws-0228-main-merge` instead of `main`
- the canonical integrated proof is receipt `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply`, which advances the protected mainline surfaces to repository version `0.177.71` and platform version `0.130.49`

## Notes

- the isolated-worktree receipt `2026-03-28-adr-0228-windmill-default-operations-surface-live-apply` remains the first-live proof for ADR 0228; this mainline receipt is the integrated release proof
- the only operational warning left in the representative workflow set is token-rotation hygiene for `local-platform-cli`, which `audit_token_inventory` now reports as `rotation_due_soon`
