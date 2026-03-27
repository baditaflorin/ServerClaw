# Workstream ADR 0175: Cross-Workstream Interface Contracts

- ADR: [ADR 0175](../adr/0175-cross-workstream-interface-contracts.md)
- Title: Machine-readable interface contracts for shared workstream boundaries and live-apply handoffs
- Status: merged
- Branch: `codex/adr-0175-interface-contracts`
- Worktree: `../worktree-adr-0175-interface-contracts`
- Owner: codex
- Depends On: `adr-0079-playbook-decomposition`, `adr-0158-config-merge-protocol`
- Conflicts With: none
- Shared Surfaces: `config/contracts/`, `platform/interface_contracts.py`, `scripts/interface_contracts.py`, `scripts/validate_repository_data_models.py`, `Makefile`, `workstreams.yaml`, `docs/runbooks/cross-workstream-interface-contracts.md`

## Scope

- add a dedicated contract registry under `config/contracts/`
- validate the workstream registry as a shared producer-consumer boundary
- validate the `converge-*` workflow to live-apply handoff across Make targets, workflow contracts, command contracts, and runbooks
- make the generic live-apply entrypoints run a contract guard before the playbook starts

## Non-Goals

- retrofitting every historic repository boundary in one change
- changing runtime execution ordering or lock semantics
- performing a production live apply for this repo-only contract work

## Expected Repo Surfaces

- `config/contracts/workstream-registry-v1.yaml`
- `config/contracts/converge-workflow-live-apply-v1.yaml`
- `platform/interface_contracts.py`
- `scripts/interface_contracts.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `tests/test_interface_contracts.py`
- `docs/runbooks/cross-workstream-interface-contracts.md`
- `docs/adr/0175-cross-workstream-interface-contracts.md`
- `docs/workstreams/adr-0175-cross-workstream-interface-contracts.md`

## Expected Live Surfaces

- no direct live platform mutation
- generic live-apply commands stop early if the repo-side contract guard fails

## Verification

- Run `uvx --from pyyaml python scripts/interface_contracts.py --validate`
- Run `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:n8n`
- Run `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply group:automation`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run `uv run --with pytest python -m pytest tests/test_interface_contracts.py tests/test_release_manager.py tests/test_live_apply_receipts.py -q`

## Merge Criteria

- the contract registry validates cleanly on current `main`
- the workstream registry exposes a stable required field set with unique ids
- the `converge-*` workflow handoff to live-apply surfaces stays machine-checkable
- generic live-apply entrypoints enforce the contract guard before ansible starts

## Outcome

- repository implementation completed in `0.176.1`
- the first contract set covers the shared workstream registry and the live-apply converge workflow surface
- no platform version bump was required because this change is repo-only

## Notes For The Next Assistant

- Extend `config/contracts/` when a shared boundary appears in more than one active workstream; keep the contract validator close to the boundary rather than embedding new ad hoc checks in unrelated scripts.
- Use the live-apply guard for repo-side verification only. It validates contracts and target playbooks, but it does not replace workflow-specific preflight or post-apply receipts.
