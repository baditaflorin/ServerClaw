# Workstream WS-0231: Local Secret Delivery Live Apply

- ADR: [ADR 0231](../adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md)
- Title: Live apply host-native secret delivery via OpenBao Agent and systemd credentials
- Status: live_applied
- Implemented In Repo Version: 0.177.44
- Live Applied In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0231-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-live-apply`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0051-control-plane-backup-recovery-and-break-glass`, `adr-0077-compose-runtime-secrets-injection`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`, `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.hcl.j2`, `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.service.j2`, `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/`, `docs/runbooks/configure-control-plane-recovery.md`, `docs/adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md`, `tests/test_compose_runtime_secret_injection.py`, `workstreams.yaml`

## Scope

- add a reusable repo-managed helper that delivers host-native secrets through an OpenBao Agent supervised by systemd
- migrate the live `lv3-control-plane-backup` unit on `docker-runtime-lv3` away from a guest-local OpenBao token file and a plaintext DSN baked into the script
- verify the new systemd credential path end to end on the live platform from the latest `origin/main`
- record branch-local evidence, receipts, and merge notes without mutating protected release truth until the final integration step

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.hcl.j2`
- `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.service.j2`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/templates/lv3-control-plane-backup.service.j2`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/templates/lv3-control-plane-backup.sh.j2`
- `docs/runbooks/configure-control-plane-recovery.md`
- `docs/workstreams/ws-0231-live-apply.md`
- `docs/adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md`
- `docs/adr/.index.yaml`
- `tests/test_compose_runtime_secret_injection.py`
- `receipts/live-applies/2026-03-28-adr-0231-local-secret-delivery-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` runs `lv3-control-plane-backup-openbao-agent.service` as the host-native credential delivery path for `lv3-control-plane-backup.service`
- `/run/lv3-systemd-credentials/control-plane-backup/` contains only the runtime credential sources needed by systemd for the backup unit
- `/etc/lv3/control-plane-recovery/openbao-backup-token.json` is absent after convergence
- starting `lv3-control-plane-backup.service` succeeds with the new credential delivery path and produces a fresh backup generation on `backup-lv3`

## Verification

- `uv run --with pytest pytest -q tests/test_compose_runtime_secret_injection.py`
- `make syntax-check-control-plane-recovery`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- `make validate`
- `make converge-control-plane-recovery`
- live checks on `docker-runtime-lv3` for `lv3-control-plane-backup-openbao-agent.service`, `lv3-control-plane-backup.service`, `/run/lv3-systemd-credentials/control-plane-backup/`, and the absence of `/etc/lv3/control-plane-recovery/openbao-backup-token.json`

## Outcome

- the repo now includes a reusable host-native secret helper at [`collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-live-apply/collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml) that provisions OpenBao AppRole bootstrap material, renders agent configuration and templates, and supervises the agent under systemd with a direct `/bin/vault` entrypoint inside the pinned OpenBao image
- `docker-runtime-lv3` now runs [`lv3-control-plane-backup-openbao-agent.service`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-live-apply/collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.service.j2) as the host-native credential source for [`lv3-control-plane-backup.service`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-live-apply/collections/ansible_collections/lv3/platform/roles/control_plane_recovery/templates/lv3-control-plane-backup.service.j2), with `/run/lv3-systemd-credentials/control-plane-backup/openbao-token` and `/run/lv3-systemd-credentials/control-plane-backup/windmill-db-dsn` present at mode `0600`
- the legacy `/etc/lv3/control-plane-recovery/openbao-backup-token.json` artifact is absent on `docker-runtime-lv3`, the immediate backup replay completed successfully at `2026-03-28 16:44:35 UTC`, `backup-lv3` now holds fresh generation `20260328T164431Z`, and the restore drill re-passed at `2026-03-28T16:45:06Z`
- repository version `0.177.44` integrated the workstream into `main` without a platform-version bump because the live replay was already verified on platform version `0.130.38`

## Mainline Integration

- repository version `0.177.44` now carries the protected integration updates in `README.md`, `VERSION`, `changelog.md`, `RELEASE.md`, `docs/release-notes/0.177.44.md`, and `versions/stack.yaml`
- canonical truth now maps `control_plane_recovery` to receipt `2026-03-28-adr-0231-local-secret-delivery-live-apply`; the current `main` baseline sits at platform version `0.130.40`, while ADR 0231 itself first became true on `0.130.38`

## Notes For The Next Assistant

- the successful live replay required two helper fixes after the first host attempt: bypass the OpenBao image entrypoint with `/bin/vault`, and emit integer permission bits (`384`) in the agent HCL instead of quoted strings
- if `lv3-control-plane-backup-openbao-agent.service` regresses, check the service journal first for container bootstrap errors before assuming the AppRole or KV payload is wrong
- the protected integration follow-up is complete; future changes should preserve the host-native credential path and the stable receipt mapping now recorded on `main`
