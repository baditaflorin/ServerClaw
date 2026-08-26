# Workstream WS-0382: Keycloak Interactive Login Closure

- ADR: [ADR 0382](../adr/0382-keycloak-sign-in-button-stuck-postmortem.md)
- Title: Keycloak Sign-In Button Stuck
- Status: live_applied
- Included In Repo Version: `0.178.144`
- Included In Platform Version: `0.178.144`
- Branch-Local Receipt: `receipts/live-applies/ws-0382-live-apply-apply-receipt.yaml`
- Mainline Receipt: `receipts/live-applies/2026-04-15-adr-0382-keycloak-sign-in-button-stuck-mainline-live-apply.json`
- Latest Verified Base: `origin/main@d86bd43709f5319338def284988a907559ff9f9c` (`repo 0.178.143`, `platform 0.178.143`)
- Branch: `codex/ws-0382-main-integration-r3`
- Worktree: `.worktrees/ws-0382-main`
- Owner: `codex`
- Depends On: `adr-0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps`, `adr-0381-login-service-contracts-and-session-recovery-automation`
- Conflicts With: none
- Shared Surfaces: `playbooks/keycloak.yml`, `playbooks/services/keycloak.yml`, `inventory/group_vars/all/platform_services.yml`, `inventory/host_vars/proxmox-host.yml`, `scripts/session_logout_verify.py`, `scripts/restic_config_backup.py`, `roles/nginx_edge_publication/tasks/main.yml`, `roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`, `tests/test_keycloak_playbook.py`, `tests/test_session_logout_verify.py`, `tests/test_nginx_edge_publication_role.py`, `tests/test_restic_config_backup.py`, `docs/adr/0382-keycloak-sign-in-button-stuck-postmortem.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/keycloak-down.md`, `workstreams.yaml`, `receipts/live-applies/`, `receipts/restic-backups/`, `receipts/restic-restore-verifications/`, `receipts/restic-snapshots-latest.json`

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
  historical `/srv/platform_server/...` snapshot paths. The verifier now
  resolves restored content from the snapshot’s recorded paths, and the managed
  production restore verification passes again.

## Verification

- Generated topology refresh stayed current:
  - `python3 scripts/generate_platform_vars.py --check`
  - `uv run --with pyyaml python scripts/generate_cross_cutting_artifacts.py --check`
- Targeted regression slices passed:
  - `uv run --with pytest --with pyyaml pytest tests/test_keycloak_playbook.py tests/test_session_logout_verify.py tests/test_nginx_edge_publication_role.py tests/test_restic_config_backup.py -q`
- Governed latest-main production replay passed:
  - `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=keycloak env=production`
  - play recap: `monitoring ok=20 changed=0`, `nginx ok=49 changed=4`,
    `postgres ok=81 changed=0`, `proxmox-host ok=373 changed=0`,
    `runtime-control ok=267 changed=8`
- Public-path verification passed:
  - OIDC discovery returned `HTTP 200`
  - `uv run --with playwright python scripts/session_logout_verify.py ...`
    returned `verified shared edge logout via https://home.example.com/` and
    `verified Outline logout via https://wiki.example.com/auth/oidc`
- Governed restic automation passed:
  - the live-apply wrapper synced `receipts/restic-backups/20260415T070357Z.json`
    plus `receipts/restic-snapshots-latest.json`
  - `python scripts/trigger_restic_live_apply.py --env production --mode restore-verify --triggered-by ws-0382-mainline-restore-verify`
    synced `receipts/restic-restore-verifications/20260415T070524Z.json` and
    restored `4652` receipt files from the historical
    `/srv/platform_server/receipts` snapshot root

## Live Evidence

- Latest-main replay on `origin/main@d86bd43709f5319338def284988a907559ff9f9c`
  (`repo/platform 0.178.143`):
  - `receipts/live-applies/evidence/2026-04-15-ws-0382-mainline-keycloak-live-apply-r1-0.178.143.txt`
  - `receipts/live-applies/evidence/2026-04-15-ws-0382-mainline-oidc-discovery-r1-0.178.143.txt`
  - `receipts/live-applies/evidence/2026-04-15-ws-0382-mainline-session-logout-verify-r1-0.178.143.txt`
  - `receipts/live-applies/evidence/2026-04-15-ws-0382-mainline-restic-restore-verify-r1-0.178.143.txt`
  - `receipts/restic-backups/20260415T070357Z.json`
  - `receipts/restic-restore-verifications/20260415T070524Z.json`
  - `receipts/restic-snapshots-latest.json`
- Historical `0.178.140` branch-local evidence retained for provenance:
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-keycloak-live-apply-0.178.140.txt`
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-session-logout-verify-0.178.140.txt`
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-live-apply-trigger-0.178.140.txt`
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-restore-verify-0.178.140.txt`
  - `receipts/live-applies/evidence/2026-04-14-ws-0382-restic-restore-verify-rerun-0.178.140.txt`

## Mainline Integration Notes

- This workstream is integrated into repo and platform version `0.178.144`.
- The merged closeout archives the active workstream entry, regenerates the
  workstream and ADR discovery surfaces, updates the ADR implementation
  metadata, and records the latest-main live-apply evidence in the canonical
  release and stack state.
