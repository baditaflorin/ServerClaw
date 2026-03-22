# Workstream ADR 0051: Control-Plane Backup, Recovery, And Break-Glass

- ADR: [ADR 0051](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0051-control-plane-backup-recovery-and-break-glass.md)
- Title: Recovery policy for control-plane components
- Status: live_applied
- Branch: `codex/adr-0051-control-plane-backup-recovery-break-glass`
- Worktree: `../proxmox_florin_server-adr-0051`
- Owner: codex
- Depends On: `adr-0029-backup-vm`, `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0044-windmill`, `adr-0041-email-platform`
- Conflicts With: none
- Shared Surfaces: PBS backups, recovery metadata, break-glass procedures

## Scope

- define recovery scope for the new control-plane apps and credentials
- make backup and restore expectations explicit
- document break-glass dependencies and failure modes

## Non-Goals

- completing every restore drill in this planning workstream
- assuming VM-level backup alone is sufficient

## Expected Repo Surfaces

- `docs/adr/0051-control-plane-backup-recovery-and-break-glass.md`
- `docs/workstreams/adr-0051-control-plane-recovery.md`
- `docs/runbooks/configure-control-plane-recovery.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `playbooks/control-plane-recovery.yml`
- `roles/control_plane_recovery/`
- `roles/control_plane_recovery_store/`
- `roles/control_plane_recovery_controller/`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `Makefile`
- `workstreams.yaml`

## Expected Live Surfaces

- scheduled backup coverage and restore guidance for `step-ca`, OpenBao, Windmill, and mail-control data
- mirrored controller-local recovery bundle on `backup-lv3`
- explicit break-glass recovery paths for loss of routine automation
- recurring restore drill evidence on `backup-lv3`

## Verification

- `make syntax-check-control-plane-recovery`
- `make converge-control-plane-recovery`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'sudo cat /srv/control-plane-recovery/drills/last-restore-drill.json'`

## Merge Criteria

- the repo exposes a repeatable control-plane recovery workflow with scheduled backup and restore-drill surfaces
- the live platform lands control-plane archives plus controller recovery references on `backup-lv3`
- the restore drill passes against the latest runtime archives and mirrored controller bundle

## Notes For The Next Assistant

- Live apply completed on `2026-03-22` with `lv3-control-plane-backup.timer` active on `docker-runtime-lv3` and `lv3-control-plane-restore-drill.timer` active on `backup-lv3`.
- The latest restore drill now records a structured pass result at `/srv/control-plane-recovery/drills/last-restore-drill.json`.
- The controller recovery bundle intentionally excludes the private break-glass SSH key; preserve `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519` separately.
