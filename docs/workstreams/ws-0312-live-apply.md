# Workstream ws-0312-live-apply: Shared Notification Center And Activity Timeline Across Human Surfaces

- ADR: [ADR 0312](../adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md)
- Title: Live apply the shared notification center and activity timeline into the interactive ops portal from the latest `origin/main`
- Status: in_progress
- Branch: `codex/ws-0312-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0312-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0307-platform-workbench-as-the-cohesive-first-party-app-frame`, `adr-0309-task-oriented-information-architecture-across-the-platform-workbench`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/app.py`, `scripts/ops_portal/static/portal.css`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/attention.html`, `scripts/ops_portal/templates/partials/changelog.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/docker-compose.yml.j2`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/ops-portal.env.j2`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/ops-portal-down.md`, `docs/workstreams/ws-0312-live-apply.md`, `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`, `docs/adr/.index.yaml`, `workstreams.yaml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_runtime_role.py`, `tests/test_ops_portal_playbook.py`, `receipts/live-applies/2026-04-02-adr-0312-shared-notification-center-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-adr-0312-*`

## Scope

- add a first live notification center to the interactive ops portal for actionable operator items
- add a shared activity timeline that combines recent portal-visible history with notification acknowledgement events
- persist acknowledge and dismiss state in a repo-managed runtime state path instead of browser-only session data
- update the ops portal deployment contract, verification tasks, and operator runbooks to cover the new attention surface

## Non-Goals

- implementing ADR 0308, ADR 0310, ADR 0311, ADR 0313, ADR 0314, ADR 0315, or ADR 0316 in the same branch
- rewriting protected release files on this workstream branch before the final integration step
- replacing the changelog portal, Mattermost, ntfy, or product-native alert UIs

## Expected Repo Surfaces

- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/attention.html`
- `scripts/ops_portal/templates/partials/changelog.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/docker-compose.yml.j2`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/ops-portal.env.j2`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/ops-portal-down.md`
- `docs/workstreams/ws-0312-live-apply.md`
- `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_ops_portal_playbook.py`
- `receipts/live-applies/2026-04-02-adr-0312-shared-notification-center-live-apply.json`
- `receipts/live-applies/evidence/2026-04-02-adr-0312-*`

## Expected Live Surfaces

- `https://ops.lv3.org` exposes a dedicated attention center section with actionable notifications
- notification acknowledge and dismiss actions survive refreshes because the state is persisted under the managed ops-portal runtime path
- the shared activity timeline shows recent live applies, promotions, and notification state changes in one browser-visible history

## Verification

- focused portal contract tests:
  `uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal_playbook.py -q`
- repo validation gate:
  `./scripts/validate_repo.sh agent-standards`
- live replay:
  governed `ops_portal` production replay from this exact worktree with the documented `ops_portal_repo_root` override

## Merge Notes

- protected release surfaces still need the normal final integration step after the live apply is verified
- if the branch finishes live-applied before merge-to-main, the remaining work is limited to release-truth updates, ADR metadata finalization, and any required `main`-only platform version bookkeeping
