# Workstream ADR 0100: RTO/RPO Targets and Disaster Recovery Playbook

- ADR: [ADR 0100](../adr/0100-rto-rpo-targets-and-disaster-recovery-playbook.md)
- Title: Formal RTO < 4h / RPO < 24h targets, repo-managed DR readiness reporting, and off-site recovery path for `backup`
- Status: merged
- Branch: `codex/adr-0100-dr-playbook`
- Worktree: `.worktrees/adr-0100`
- Owner: codex
- Depends On: `adr-0020-backups`, `adr-0029-backup-vm`, `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0051-control-plane-backup`, `adr-0098-postgres-ha`, `adr-0099-backup-restore-verification`
- Conflicts With: none
- Shared Surfaces: `playbooks/backup-vm.yml`, `roles/proxmox_backups/`, Windmill workflow seeds, `docs/runbooks/`

## Scope

- write `scripts/disaster_recovery_runbook.py`
- seed Windmill wrapper `config/windmill/scripts/disaster-recovery-runbook.py`
- add `config/disaster-recovery-targets.json`
- write `scripts/generate_dr_report.py`
- add `make dr-status`
- add `lv3 release status`
- document the operator runbook and break-glass references
- wire the optional off-site backup of VM `160` into the backup VM playbook
- record a DR table-top review receipt

## Non-Goals

- autonomous disaster recovery execution
- second-site active replication
- pretending the off-site storage path is already live when credentials are not yet configured

## Expected Repo Surfaces

- `config/disaster-recovery-targets.json`
- `scripts/disaster_recovery_runbook.py`
- `config/windmill/scripts/disaster-recovery-runbook.py`
- `scripts/generate_dr_report.py`
- `scripts/lv3_cli.py`
- `playbooks/backup-vm.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_backups/`
- `docs/runbooks/disaster-recovery.md`
- `docs/runbooks/break-glass.md`
- `receipts/dr-table-top-reviews/`

## Expected Live Surfaces

- the current live platform still shows no off-site storage configured until Storage Box credentials are supplied at apply time
- `backup` remains the PBS recovery anchor VM
- Windmill can seed the repo-managed DR wrapper on the next Windmill converge from `main`

## Verification

- `python3 scripts/generate_dr_report.py`
- `python3 scripts/generate_dr_report.py --format release`
- `python3 scripts/disaster_recovery_runbook.py --format json`
- `python3 scripts/lv3_cli.py release status`
- `make dr-status`
- `make syntax-check-backup-vm`

## Merge Criteria

- DR targets are machine-readable
- the repo ships a DR readiness report and operator CLI surface
- the recovery order matches the current VM layout
- the backup playbook can optionally converge the off-site `backup` copy
- the ADR and workstream metadata reflect completed repository implementation

## Notes For The Next Assistant

- The off-site copy is intentionally modeled as a Proxmox backup of VM `160`, not PBS native sync.
- Live apply remains blocked until `PROXMOX_DR_OFFSITE_*` values are supplied for the external storage target.
- The current table-top review receipt records the gap honestly: DR process reviewed, off-site storage not yet applied live.
