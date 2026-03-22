# Workstream ADR 0051: Control-Plane Backup, Recovery, And Break-Glass

- ADR: [ADR 0051](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0051-control-plane-backup-recovery-and-break-glass.md)
- Title: Recovery policy for control-plane components
- Status: merged
- Branch: `codex/adr-0051-control-plane-recovery`
- Worktree: `../proxmox_florin_server-control-plane-recovery`
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
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- backup coverage and restore guidance for `step-ca`, OpenBao, Windmill, and mail-control data
- explicit break-glass recovery paths for loss of routine automation

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0051-control-plane-backup-recovery-and-break-glass.md`

## Merge Criteria

- the ADR defines control-plane state explicitly
- the workstream keeps recovery and break-glass in scope from the start

## Notes For The Next Assistant

- do not treat backup as complete until restore drills exist for the new control-plane apps
