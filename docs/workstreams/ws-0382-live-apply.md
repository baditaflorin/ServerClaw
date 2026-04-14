# Workstream WS-0382: Keycloak Interactive Login Closure

- ADR: [ADR 0382](../adr/0382-keycloak-sign-in-button-stuck-postmortem.md)
- Title: Keycloak Sign-In Button Stuck
- Status: in_progress
- Branch: `codex/ws-0382-main-integration-r2`
- Worktree: `.worktrees/ws-0382-main`
- Owner: `codex`
- Depends On: `adr-0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps`, `adr-0381-login-service-contracts-and-session-recovery-automation`
- Conflicts With: none
- Shared Surfaces: `playbooks/keycloak.yml`, `playbooks/services/keycloak.yml`, `inventory/group_vars/all/platform_services.yml`, `inventory/host_vars/proxmox-host.yml`, `scripts/session_logout_verify.py`, `roles/nginx_edge_publication/tasks/main.yml`, `roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `tests/test_nginx_edge_publication_role.py`, `docs/adr/0382-keycloak-sign-in-button-stuck-postmortem.md`, `docs/runbooks/configure-keycloak.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- replay ADR 0382 from the latest `origin/main` baseline rather than the earlier
  docker-runtime-only lane
- verify the current Keycloak converge path, restic trigger, and interactive
  login/logout behavior end to end
- leave merge-safe workstream, ADR, and receipt evidence for final integration
  onto `main`

## Non-Goals

- carrying forward stale ws-0382 assumptions that predate the runtime-control
  topology updates already merged onto `origin/main`
- bumping `VERSION`, editing release sections in `changelog.md`, or updating
  the top-level `README.md` before the final main integration step
- broad unrelated auth/platform cleanup outside the Keycloak interactive login
  incident

## Current Baseline

- `origin/main` head: `c6f9564acb39c3927a805574a30da3e51833c1ad`
- `VERSION`: `0.178.138`
- `versions/stack.yaml` repo/platform version: latest integrated mainline state
- current mainline Keycloak converge target: `runtime-control`
- current mainline OpenBao converge target: `runtime-control`
- OpenBao secret metadata for
  `services/restic-config-backup/runtime-config` is still version `6` from
  `2026-03-31T21:06:13Z`
- the current controller-local restic password, OpenBao version `6`, and the
  live `/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json`
  payload now match again

## Planned Verification

- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- targeted latest-main tests around Keycloak/session verification
- governed production replay via
  `make live-apply-service service=keycloak env=production ALLOW_IN_PLACE_MUTATION=true`
- explicit restic verification if the live-apply path does not already leave a
  fresh successful snapshot receipt
- `scripts/session_logout_verify.py` against the production `*.lv3.org` URLs

## Notes

- The previous ws-0382 branch captured useful evidence, but its repo-side
  topology assumptions were overtaken by mainline commits that moved Keycloak
  and OpenBao contract surfaces onto `runtime-control`.
- This workstream exists to prove the incident status against the actual latest
  mainline, then update ADR 0382 truthfully from that replay.
- The latest-main replay also exposed an exact-main edge TLS regression on the
  `nginx` host: the shared SAN certificate exists as `lv3-edge-0001`, but the
  edge role currently only treats the unsuffixed `lv3-edge` lineage as the
  shared certificate path, which drops HTTPS server blocks for `home.lv3.org`
  and `sso.lv3.org` and serves the fallback `browser.lv3.org` cert instead.
