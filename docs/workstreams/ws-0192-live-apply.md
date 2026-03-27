# Workstream ws-0192-live-apply: Live Apply ADR 0192 From Latest `origin/main`

- ADR: [ADR 0192](../adr/0192-separate-capacity-classes-for-standby-recovery-and-preview-workloads.md)
- Title: production replay of separated capacity classes for standby, recovery, and preview automation
- Status: live_applied
- Branch: `codex/ws-0192-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0192-live-apply`
- Owner: codex
- Depends On: `adr-0105-capacity-model`, `adr-0180-standby-capacity`, `adr-0183-auxiliary-cloud-failure-domain`, `adr-0186-prewarmed-fixture-pools`
- Conflicts With: none
- Shared Surfaces: `config/capacity-model.json`, `docs/schema/capacity-model.schema.json`, `scripts/capacity_report.py`, `scripts/fixture_manager.py`, `scripts/restore_verification.py`, `scripts/validate_ephemeral_vmid.py`, `docs/runbooks/capacity-classes.md`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- classify protected spare capacity into `ha_reserved`, `recovery_reserved`, and `preview_burst`
- expose class summaries and admission results through machine-readable and operator-facing capacity reports
- enforce `preview_burst` on the fixture path and gate restore verification through `recovery_reserved` admission rules
- replay the controller-side operator paths against the live platform from this isolated worktree and record evidence

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_capacity_report.py tests/test_fixture_manager.py tests/test_restore_verification.py tests/test_standby_capacity.py tests/test_validate_ephemeral_vmid.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make capacity-report NO_LIVE_METRICS=true`
- `make capacity-report`
- `uv run --with pyyaml python scripts/capacity_report.py --check-class-request --requester-class preview --proposed-change 4,2,32`
- `uv run --with pyyaml python scripts/capacity_report.py --check-class-request --requester-class restore-verification --declared-drill --proposed-change 4,2,48`
- `uv run --with pyyaml python scripts/fixture_manager.py list --no-refresh-health`

## Outcome

- implementation commit `40df293577053160f03a901ab316c26e58d22974` adds explicit `capacity_class` metadata to the capacity model and schema
- `make capacity-report NO_LIVE_METRICS=true` and `make capacity-report` both rendered the new class summaries from this worktree, with the live path reporting `Metrics source: ssh+influx`
- the preview admission check approved `4,2,32` inside `preview_burst`, and the declared restore-drill admission check approved `4,2,48` inside `recovery_reserved`
- `uv run --with pyyaml python scripts/fixture_manager.py list --no-refresh-health` returned `No active fixtures`, so the live preview occupancy was zero at verification time
- `./scripts/validate_repo.sh data-models` still fails on the unrelated mainline issue `playbooks/proxmox-staging-bridge.yml` missing an ansible-scope-runner leaf catalog entry; the ADR 0192 focused validation surfaces passed
- merge-to-main still needs the protected integration files updated separately: `README.md`, `VERSION`, `changelog.md`, and `versions/stack.yaml`

## Merge Criteria

- `config/capacity-model.json` declares all three classes explicitly in branch-local truth
- preview fixtures remain limited to `preview_burst` unless an operator uses explicit break-glass evidence
- restore drills can consume `recovery_reserved` and borrow `preview_burst` only when declared as a drill
- merge-to-main still needs the protected integration files updated separately: `README.md`, `VERSION`, `changelog.md`, and `versions/stack.yaml`
