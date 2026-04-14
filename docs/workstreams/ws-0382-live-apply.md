# Workstream WS-0382: Keycloak Interactive Login Closure

- ADR: [ADR 0382](../adr/0382-keycloak-sign-in-button-stuck-postmortem.md)
- Title: Keycloak Sign-In Button Stuck
- Status: ready
- Latest Verified Base: `origin/main@4bb9c2fd7c8a3296e33a8dc7e77ee06bd5adf0a4` (`repo 0.178.140`, `platform 0.178.138`)
- Branch: `codex/ws-0382-main-integration-r2`
- Worktree: `.worktrees/ws-0382-main`
- Owner: `codex`
- Depends On: `adr-0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps`, `adr-0381-login-service-contracts-and-session-recovery-automation`
- Conflicts With: none
- Shared Surfaces: `playbooks/keycloak.yml`, `playbooks/services/keycloak.yml`, `inventory/group_vars/all/platform_services.yml`, `inventory/host_vars/proxmox-host.yml`, `scripts/session_logout_verify.py`, `scripts/restic_config_backup.py`, `roles/nginx_edge_publication/tasks/main.yml`, `roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `tests/test_keycloak_playbook.py`, `tests/test_session_logout_verify.py`, `tests/test_nginx_edge_publication_role.py`, `tests/test_restic_config_backup.py`, `docs/adr/0382-keycloak-sign-in-button-stuck-postmortem.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/keycloak-down.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- replay ADR 0382 from the latest `origin/main` baseline instead of relying on
  older docker-runtime-era assumptions
- verify the governed Keycloak live-apply path, shared-edge login/logout flow,
  and restic automation path end to end
- leave merge-safe workstream, receipt, and runbook state before the final
  protected-file integration on `main`

## Non-Goals

- speculative version bumps or protected release-state edits before the final
  integration step
- broad auth cleanup outside the Keycloak incident and the automation defects
  exposed while verifying it
- overwriting unrelated concurrent work on `origin/main`

## Outcome

- The latest realistic mainline already had Keycloak and OpenBao correctly
  placed on `runtime-control`; the remaining user-visible breakage on exact-main
  came from the shared-edge TLS lineage lookup, which only trusted the
  unsuffixed `lv3-edge` lineage while the live certificate had rotated to
  `lv3-edge-0001`.
- `nginx_edge_publication` now resolves the effective public certificate lineage
  from the live Let’s Encrypt directory and keeps the `home` and `sso` server
  blocks published even after Certbot suffix rotation.
- The governed production replay of `make live-apply-service service=keycloak`
  succeeded from the latest `origin/main` base, and the shared-edge logout
  automation now verifies cleanly again.
- Repo automation verification also exposed a false-negative restore-verify bug:
  the restic verifier assumed the current runtime repo root and could not follow
  historical `/srv/proxmox_florin_server/...` snapshot paths. The verifier now
  resolves restored content from the snapshot’s recorded paths, and the managed
  production restore verification passes again.

## Verification

- Generated topology refresh stayed current:
  `python3 scripts/generate_platform_vars.py --check`
- Validation gates passed:
  - `./scripts/validate_repo.sh agent-standards`
  - `./scripts/validate_repo.sh workstream-surfaces`
- Targeted regression slices passed:
  - `uv run --with pytest --with pyyaml pytest tests/test_keycloak_playbook.py tests/test_session_logout_verify.py tests/test_nginx_edge_publication_role.py -q`
  - `uv run --with pytest --with pyyaml pytest tests/test_restic_config_backup.py -q`
- Governed production replay passed:
  - `make live-apply-service service=keycloak env=production ALLOW_IN_PLACE_MUTATION=true`
- Public-path verification passed:
  - the OIDC discovery endpoint returned `HTTP 200`
  - the shared-edge home redirect chain completed back to the Keycloak login page
  - `uv run --with playwright python scripts/session_logout_verify.py ...` returned:
    - `verified shared edge logout via https://home.lv3.org/`
    - `verified Outline logout via https://wiki.lv3.org/auth/oidc`
- Governed restic automation passed:
  - `python scripts/trigger_restic_live_apply.py --env production --mode backup --triggered-by ws-0382-post-verify --live-apply-trigger`
    returned `status=ok` and synced
    `receipts/restic-backups/20260414T084809Z.json` plus
    `receipts/restic-snapshots-latest.json`
  - `python scripts/trigger_restic_live_apply.py --env production --mode restore-verify --triggered-by ws-0382-post-verify-restore-rerun`
    returned `status=ok`, synced
    `receipts/restic-restore-verifications/20260414T085430Z.json`, and restored
    `4642` receipt files from the historical receipts snapshot

## Live Evidence

- Keycloak live apply:
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-keycloak-live-apply-0.178.140.txt`
- Session/logout verification:
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-session-logout-verify-0.178.140.txt`
- Restic backup trigger:
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-live-apply-trigger-0.178.140.txt`
  - `receipts/restic-backups/20260414T084809Z.json`
  - `receipts/restic-snapshots-latest.json`
- Restore verification:
  - first failing proof before the fix:
    `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-restore-verify-0.178.140.txt`
  - successful rerun after the snapshot-path fix:
    `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-restore-verify-rerun-0.178.140.txt`
    and `receipts/restic-restore-verifications/20260414T085430Z.json`

## Mainline Integration Notes

- Protected integration files still intentionally wait for the final `main`
  closeout step: `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`,
  release-note indexes, ADR 0382 implementation-version metadata, and the
  archived workstream registry entry.
- The merge-to-main step must archive the active workstream YAML, regenerate
  `workstreams.yaml`, cut the next release version, and stamp the verified live
  apply into `versions/stack.yaml` and the ADR metadata from the merged tree.
