# Workstream ws-0240-main-merge

- ADR: [ADR 0240](../adr/0240-operator-visualization-panels-via-apache-echarts.md)
- Title: Integrate ADR 0240 operator visualization panels into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.64
- Platform Version Observed During Merge: 0.130.46
- Release Date: 2026-03-29
- Branch: `codex/ws-0240-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0240-main-merge`
- Owner: codex
- Depends On: `ws-0240-live-apply`

## Purpose

Carry the verified ADR 0240 Apache ECharts rollout onto the latest
`origin/main` after Harbor advanced the mainline to `0.177.63`, cut release
`0.177.64`, re-apply the exact integrated
interactive ops portal payload on `docker-runtime`, and refresh the
protected canonical-truth surfaces once the public edge is re-verified.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0240-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.64.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0240-operator-visualization-panels-via-apache-echarts.md`
- `docs/workstreams/ws-0240-live-apply.md`
- `docs/runbooks/ops-portal-down.md`
- `scripts/ops_portal/app.py`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_interactive_ops_portal.py`
- `receipts/live-applies/2026-03-28-adr-0240-operator-visualization-panels-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply.json`

## Verification

- `git merge --no-ff origin/main` refreshed this worktree onto the latest main
  baseline after `origin/main` advanced with ADR 0239 post-merge replay and the
  generated dependency-graph refresh
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.46 after the exact-main ADR 0240 replay re-verifies the Apache ECharts-backed operator visualization panels on ops.example.com while preserving the authenticated edge contract on top of the 0.130.45 baseline" --dry-run`
  reported `Current version: 0.177.63`, `Next version: 0.177.64`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.46 after the exact-main ADR 0240 replay re-verifies the Apache ECharts-backed operator visualization panels on ops.example.com while preserving the authenticated edge contract on top of the 0.130.45 baseline"`
  prepared release `0.177.64`
- `make syntax-check-ops-portal`, `make preflight WORKFLOW=converge-ops-portal`,
  `make validate-data-models`, `./scripts/validate_repo.sh agent-standards`,
  and `uv run --with-requirements requirements/integration-tests.txt --with-requirements requirements/ops-portal.txt pytest tests/test_interactive_ops_portal.py tests/test_runtime_assurance_scoreboard.py tests/test_ops_portal.py`
  all passed from the integrated candidate
- the normal `make converge-ops-portal` wrapper and the equivalent direct
  mutation playbook launch both received local exit `143` / signal `15` from
  this Codex environment before the remote apply could emit its first task
  output, so that controller-local limitation was recorded instead of treating
  it as guest failure
- the exact `0.177.63` mainline payload was staged under
  `/tmp/ops-portal-mainline` on `docker-runtime`, promoted into
  `/opt/ops-portal/service` and `/opt/ops-portal/data`, and rebuilt with
  `docker compose up -d --build --remove-orphans`
- guest-local verification confirmed the running service hashes for
  `app.py`, `static/portal.js`, and `templates/partials/overview.html` matched
  the repository, `curl -fsS http://10.10.10.20:8092/health` returned
  `{"status":"ok"}`, and both `/` plus `/partials/overview` exposed the
  expected ECharts mount points
- `curl -ks https://ops.example.com/health` returned `{"status":"ok"}` and
  `curl -k -I https://ops.example.com` returned `HTTP/2 302` to
  `/oauth2/sign_in?rd=https://ops.example.com/` while preserving the CSP allowance
  for `https://unpkg.com`

## Outcome

- release `0.177.64` carries ADR 0240 onto `main`
- the current live platform baseline after the exact-main replay is `0.130.46`
- the canonical merged-main evidence is recorded under
  `receipts/live-applies/2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply.json`
