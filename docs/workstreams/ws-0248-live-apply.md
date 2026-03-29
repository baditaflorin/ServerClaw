# Workstream WS-0248: Session And Logout Authority Live Apply

- ADR: [ADR 0248](../adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md)
- Title: Live apply unified browser-session logout authority across Keycloak, oauth2-proxy, and app-local sign-out surfaces
- Status: live_applied
- Implemented In Repo Version: 0.177.63
- Live Applied In Platform Version: 0.130.45
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0248-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0248-live-apply`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0133-portal-authentication-by-default`, `adr-0199-outline-living-knowledge-wiki`, `adr-0247-authenticated-browser-journey-verification-via-playwright`
- Conflicts With: none
- Shared Surfaces: `inventory/group_vars/platform.yml`, `playbooks/keycloak.yml`, `playbooks/public-edge.yml`, `playbooks/outline.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/**`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/**`, `collections/ansible_collections/lv3/platform/roles/grafana_sso/**`, `collections/ansible_collections/lv3/platform/roles/outline_runtime/**`, `docs/runbooks/portal-authentication-by-default.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/configure-outline.md`, `scripts/session_logout_verify.py`, `tests/test_nginx_edge_publication_role.py`, `tests/test_keycloak_runtime_role.py`, `tests/test_session_logout_verify.py`, `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`, `workstreams.yaml`

## Scope

- make Keycloak the effective logout authority for the shared edge-protected browser estate
- ensure oauth2-proxy logout clears its session cookie and uses Keycloak RP-initiated logout with an `id_token_hint` so browser logout does not stall on a confirmation page
- align app-local logout surfaces that already manage their own local session state with the same shared logout authority path
- record live-apply evidence, branch-local verification, and merge-to-main notes without mutating protected release truth on this workstream branch

## Expected Repo Surfaces

- `inventory/group_vars/platform.yml`
- `playbooks/keycloak.yml`
- `playbooks/public-edge.yml`
- `playbooks/outline.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/grafana_sso/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/defaults/main.yml`
- `docs/runbooks/portal-authentication-by-default.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/configure-outline.md`
- `scripts/generate_platform_vars.py`
- `docs/workstreams/ws-0248-live-apply.md`
- `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`
- `scripts/session_logout_verify.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_grafana_sso_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_outline_runtime_role.py`
- `tests/test_session_logout_verify.py`
- `receipts/live-applies/2026-03-28-adr-0248-session-logout-authority-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- edge-protected services expose a repo-managed shared logout entrypoint that clears the shared oauth2-proxy cookie and completes Keycloak logout without an interactive confirmation page
- `ops.lv3.org` serves both a repo-managed proxy-cleanup path and a logged-out landing path for post-logout return
- Grafana local logout hands off to Keycloak first and then to the shared proxy-cleanup path so both the app-local session and shared edge cookie are cleared
- Outline local logout hands off to Keycloak with the same shared proxy-cleanup return path so app-local and shared-edge logout semantics stay aligned
- revisiting a protected surface after logout yields the expected unauthenticated redirect or challenge path instead of silent re-entry

## Verification

- repo checks for the affected role templates and logout verifier
- syntax checks for `keycloak`, `public-edge`, and `outline`
- branch-local live convergence from latest `origin/main`
- end-to-end browser-session verification on at least one shared edge-protected surface and one app-local logout surface
- receipt recorded under `receipts/live-applies/`

## Live Apply Outcome

- `git fetch origin main --prune` confirmed this worktree was rebased onto the
  latest `origin/main` before the final live replay and verification pass.
- `make live-apply-service service=outline env=production` was exercised and
  stopped at `make check-canonical-truth` because `README.md` was stale in the
  isolated worktree and remains a protected shared integration file on
  workstream branches. That gate failure is recorded as expected branch-local
  behavior rather than a platform failure.
- The workstream therefore used the direct service guardrails and scoped runner:
  `scripts/interface_contracts.py --check-live-apply service:outline`,
  `scripts/standby_capacity.py --service outline`,
  `scripts/service_redundancy.py --check-live-apply --service outline`, and
  `scripts/immutable_guest_replacement.py --check-live-apply --service outline`
  all ran, with the immutable-guest plan declaring a narrow in-place exception
  that is recorded in the receipt because ADR 0248 only changes auth/logout
  wiring on the existing Outline guest.
- The first `make converge-keycloak env=production` replay failed
  transiently while reading the Outline automation user groups from the
  Keycloak admin API. A direct API check immediately after showed the
  `outline.automation` user and its expected groups were present, and the
  second replay completed successfully with
  `docker-runtime-lv3 : ok=153 changed=3 failed=0`, plus the expected
  `monitoring-lv3`, `nginx-lv3`, `postgres-lv3`, and `proxmox_florin` recaps.
- The scoped `playbooks/outline.yml` replay completed successfully from the
  isolated worktree with
  `docker-runtime-lv3 : ok=209 changed=5 failed=0`,
  `nginx-lv3 : ok=38 changed=2 failed=0`,
  `postgres-lv3 : ok=47 changed=0 failed=0`, and
  `localhost : ok=25 changed=1 failed=0`.
- `make configure-edge-publication env=production` completed successfully with
  `nginx-lv3 : ok=63 changed=5 failed=0`, reloading both oauth2-proxy and
  NGINX after the shared logout and `wiki.lv3.org` publication changes.
- Live HTTP probes confirmed:
  `https://home.lv3.org/.well-known/lv3/session/logout -> 302` to the shared
  oauth2-proxy sign-out path,
  `https://ops.lv3.org/.well-known/lv3/session/proxy-logout -> 302` to the
  logged-out landing page,
  `https://ops.lv3.org/.well-known/lv3/session/logged-out -> 200` with
  `Cache-Control: no-store`, and `https://wiki.lv3.org/` served the expected
  Outline-compatible CSP override.
- `uv run --with playwright python scripts/session_logout_verify.py --password-file .local/keycloak/outline.automation-password.txt`
  now passes end to end and verified both the shared edge logout path and the
  real Outline UI logout path. Outline still reaches the Keycloak confirmation
  page because it cannot provide `id_token_hint`; the verifier now submits that
  live confirmation form and proves both `home.lv3.org` and `wiki.lv3.org`
  require fresh Keycloak login afterward.
- `./scripts/validate_repo.sh data-models`, `uv run --with pyyaml --with jsonschema python scripts/generate_diagrams.py --check`,
  and `./scripts/validate_repo.sh agent-standards` all passed after the receipt
  workflow id was normalized to the accepted legacy ADR live-apply form and the
  generated coordination diagram was refreshed from the current workstream
  counts.
- `make validate-generated-docs` still reports a stale `README.md`, but the
  pending diff is limited to adding this workstream to the generated document
  index and merged-workstreams table. Those README mutations remain deferred to
  the merge-to-`main` integration step because this branch must not rewrite the
  protected top-level status surfaces.

## Live Evidence

- live-apply receipt:
  `receipts/live-applies/2026-03-28-adr-0248-session-logout-authority-live-apply.json`
- live source commit: `7b0bd0230482ef077c17714ad224364badf3171b`
- live verifier command:
  `uv run --with playwright python scripts/session_logout_verify.py --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/outline.automation-password.txt`

## Mainline Integration Outcome

- The isolated workstream intentionally left `VERSION`, `changelog.md`, the
  top-level `README.md` status summary, and `versions/stack.yaml` untouched.
  The exact-main integration step later updated those protected surfaces from
  `main` in repository version `0.177.69`.
- The synchronized mainline replay established the canonical receipt
  `receipts/live-applies/2026-03-29-adr-0248-session-logout-authority-mainline-live-apply.json`
  and advanced the integrated platform baseline to `0.130.47` while leaving ADR
  0248's first-live metadata unchanged at repo version `0.177.63` and platform
  version `0.130.45`.
- The guarded `make live-apply-service service=outline env=production ALLOW_IN_PLACE_MUTATION=true`
  path was exercised successfully on the exact-main candidate after a transient
  Keycloak admin-token timeout was recovered by a clean
  `make converge-keycloak env=production` replay and a successful rerun.
