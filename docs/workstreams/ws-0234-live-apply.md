# Workstream WS-0234: PatternFly Human Shell Live Apply

- ADR: [ADR 0234](../adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md)
- Title: Live apply the shared human app shell and navigation contract on the
  interactive ops portal
- Status: live_applied
- Implemented In Repo Version: 0.177.72
- Live Applied In Platform Version: 0.130.50
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0234-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0234-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`,
  `adr-0133-portal-authentication-by-default`,
  `adr-0209-use-case-services-and-thin-delivery-adapters`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `docs/adr/0234-*`,
  `docs/runbooks/ops-portal-down.md`,
  `playbooks/ops-portal.yml`,
  `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/*.yml`,
  `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`,
  `tests/test_interactive_ops_portal.py`,
  `tests/test_nginx_edge_publication_role.py`, `tests/test_ops_portal_playbook.py`,
  `tests/test_security_headers_audit.py`, `workstreams.yaml`

## Scope

- move the live interactive ops portal from repo-local hero chrome to a
  PatternFly-based shared shell
- add the ADR-required masthead, responsive primary navigation, shared section
  templates, and shared state primitives for warnings, errors, unauthorized
  states, and loading transitions
- keep product-native tools as linked destinations rather than embedding them
  into one page shell
- update the published `ops.example.com` CSP so the browser can load the pinned
  PatternFly stylesheet bundle
- verify the guest-local and published portal surfaces end to end and record a
  durable receipt before merge-to-main truth updates

## Non-Goals

- rewriting Homepage, Outline, Plane, Grafana, or other product-native UIs
- implementing ADR 0235 favorites and recent-destination behavior in the same
  change
- updating protected release truth on this workstream branch before the final
  integration step

## Expected Repo Surfaces

- `docs/workstreams/ws-0234-live-apply.md`
- `docs/adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/ops-portal-down.md`
- `playbooks/ops-portal.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/static/portal.js`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/macros/states.html`
- `scripts/ops_portal/templates/partials/action_result.html`
- `scripts/ops_portal/templates/partials/agents.html`
- `scripts/ops_portal/templates/partials/changelog.html`
- `scripts/ops_portal/templates/partials/drift.html`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `scripts/ops_portal/templates/partials/search.html`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_security_headers_audit.py`
- `receipts/live-applies/2026-03-29-adr-0234-patternfly-shell-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `ops.example.com` renders a PatternFly shell with a shared masthead, responsive
  navigation, and consistent status-state components
- `docker-runtime` serves the same shell on the guest-local ops portal
  listener
- the published edge security policy allows the pinned PatternFly stylesheet
  while keeping the portal auth-gated and same-origin for the repo-managed JS
  shell helpers

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py tests/test_nginx_edge_publication_role.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal_playbook.py tests/test_ops_portal.py tests/test_security_headers_audit.py` returned `48 passed`.
- `make syntax-check-ops-portal` passed.
- `./scripts/validate_repo.sh workstream-surfaces agent-standards` passed on the isolated workstream branch before the final integration step.
- `make live-apply-service service=ops_portal ...` failed closed on the
  workstream branch because canonical-truth generation would have rewritten the
  protected `README.md` and `versions/stack.yaml` surfaces, so the live replay
  used the governed direct sequence: `interface_contracts.py`,
  `promotion_pipeline.py`, `standby_capacity.py`,
  `service_redundancy.py`, `immutable_guest_replacement.py`, then
  `scripts/ansible_scope_runner.py` on
  `playbooks/services/ops_portal.yml`.
- The direct scoped replay had to pass
  `-e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0234-live-apply-r2`.
  Without that override the controller-side sync read from the top-level repo
  checkout and failed on missing service inputs such as
  `scripts/ops_portal/runtime_assurance.py`,
  `scripts/ops_portal/static/portal.js`, and
  `scripts/ops_portal/templates/partials/launcher.html`.
- The final ops-portal replay completed with
  `docker-runtime ok=130 changed=14 failed=0 skipped=15`.
- The public-edge replay used `service:public-edge` for
  `interface_contracts.py`, emitted the promotion bypass event for
  `public-edge`, and then ran `scripts/ansible_scope_runner.py` on
  `playbooks/services/public-edge.yml` because the capacity, redundancy, and
  immutable-guest guard scripts intentionally do not catalogue
  `public-edge`. That replay completed with
  `nginx-edge ok=61 changed=4 failed=0 skipped=14`.
- After rebasing the worktree onto `origin/main` commit
  `73fb0ec1336d7b5540f51590f4b4f9a3a136577c`, guest-local hashes and the public
  edge headers still matched the verified ADR 0234 rollout because the newly
  landed mainline commits were ADR-document changes outside the portal replay
  surfaces.

## Live Apply Outcome

- ADR 0234 is live on `ops.example.com` and on the guest-local
  `docker-runtime` listener, with the shared PatternFly shell, masthead,
  responsive navigation, and shared state components rendered from the
  interactive ops portal.
- The published edge now permits the pinned PatternFly stylesheet while keeping
  the authenticated ops portal redirect and the repo-managed same-origin
  JavaScript shell helpers intact.
- The ops-portal runtime replay now removes macOS `._*` AppleDouble sidecars
  from synced data and service trees before the container rebuild, preventing
  stale local filesystem metadata from polluting branch-local live applies.
- Competing `ops_portal` branch-local replays still share
  `/opt/ops-portal/service` on `docker-runtime`, so truthful live applies
  must obtain an uncontended replay window before asserting guest hashes.

## Live Evidence

- live-apply receipt:
  `receipts/live-applies/2026-03-29-adr-0234-patternfly-shell-live-apply.json`
- controller context:
  `receipts/live-applies/evidence/2026-03-29-adr-0234-controller-context.txt`
- guest-local hash and shell proof:
  `receipts/live-applies/evidence/2026-03-29-adr-0234-live-hashes.txt`
- public-edge header proof:
  `receipts/live-applies/evidence/2026-03-29-adr-0234-public-edge-check.txt`

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.72`
- updated `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/0.177.72.md`, `docs/release-notes/README.md`,
  `versions/stack.yaml`, `build/platform-manifest.json`, `README.md`, and the
  ADR/workstream metadata only during the final integration step
- advanced the platform version to `0.130.50` after the rebased latest-main
  proof kept the guest hashes and public-edge CSP evidence aligned with the
  verified PatternFly shell rollout

## Merge-To-Main Notes

- remaining for merge to `main`: none
