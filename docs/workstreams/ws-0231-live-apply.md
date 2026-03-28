# Workstream WS-0231: Local Secret Delivery Live Apply

- ADR: [ADR 0231](../adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md)
- Title: Live apply host-native secret delivery via OpenBao Agent and systemd credentials
- Status: in_progress
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
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/templates/control-plane-backup-windmill-dsn.ctmpl.j2`
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

## Merge Notes

- protected integration files remain intentionally untouched while this branch is still the workstream replay
- once the live apply is verified and the branch becomes the final integration step on `main`, update `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/`, `versions/stack.yaml`, and any generated truth tied to the merged release
