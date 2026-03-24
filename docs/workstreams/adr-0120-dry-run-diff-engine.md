# Workstream ADR 0120: Dry-Run Semantic Diff Engine

- ADR: [ADR 0120](../adr/0120-dry-run-semantic-diff-engine.md)
- Title: CPU-only preflight engine that computes a structured SemanticDiff for any ExecutionIntent before execution — predicts exact changed objects across Ansible, OpenTofu, Docker, DNS, TLS, and firewall surfaces
- Status: merged
- Branch: `codex/adr-0120-diff-engine`
- Worktree: `../proxmox_florin_server-diff-engine`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0085-opentofu-vm-lifecycle`, `adr-0090-platform-cli`, `adr-0112-goal-compiler`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0116-change-risk-scoring`
- Conflicts With: none
- Shared Surfaces: `platform/diff_engine/`, `config/diff-adapters.yaml`

## Scope

- create `platform/diff_engine/__init__.py`
- create `platform/diff_engine/engine.py` — `DiffEngine.compute(intent, world_state)`: dispatches to registered adapters, aggregates `ChangedObject` lists into `SemanticDiff`
- create `platform/diff_engine/schema.py` — `ChangedObject` and `SemanticDiff` dataclasses from ADR 0120
- create `platform/diff_engine/registry.py` — adapter registry: loads adapter classes from `config/diff-adapters.yaml`, instantiates on demand
- create `platform/diff_engine/adapters/ansible_adapter.py` — runs `ansible-playbook --check --diff`; parses JSON callback output; extracts `ChangedObject` per changed task
- create `platform/diff_engine/adapters/opentofu_adapter.py` — runs `tofu plan -json`; parses resource change list
- create `platform/diff_engine/adapters/docker_adapter.py` — compares desired compose state (from compose file) against current Docker API container state
- create `platform/diff_engine/adapters/dns_adapter.py` — compares desired DNS entries (from NetBox/world-state) against live resolver responses
- create `platform/diff_engine/adapters/cert_adapter.py` — compares desired certificate config against step-ca inventory from world-state
- create `config/diff-adapters.yaml` — adapter registry config: maps tool IDs to adapter class paths and enabled flag
- update `scripts/risk_scorer/context.py` and `scripts/risk_scorer/models.py` — call `DiffEngine.compute()` after compilation and embed `SemanticDiff` plus real diff counts in the compiled intent model
- update `scripts/risk_scorer/dimensions.py` — treat `unknown_count > 0` as a maximum mutation-surface penalty and escalate irreversible diffs
- update `scripts/lv3_cli.py` — render `SemanticDiff` as the structured change summary before the approval prompt and write optional compiled-intent ledger events
- write `tests/unit/test_diff_engine.py` — test each adapter independently with fixture data; test `unknown` confidence propagation; test empty diff
- write `docs/runbooks/dry-run-semantic-diff-engine.md` — operator-facing usage, adapter behavior, and verification flow

## Non-Goals

- Writing a firewall adapter in this workstream (complex nftables parsing; add as a follow-up)
- VM-level Proxmox config diffing (add as a follow-up)
- Executing any mutations — the diff engine is read-only

## Expected Repo Surfaces

- `platform/diff_engine/__init__.py`
- `platform/diff_engine/engine.py`
- `platform/diff_engine/schema.py`
- `platform/diff_engine/registry.py`
- `platform/diff_engine/adapters/ansible_adapter.py`
- `platform/diff_engine/adapters/opentofu_adapter.py`
- `platform/diff_engine/adapters/docker_adapter.py`
- `platform/diff_engine/adapters/dns_adapter.py`
- `platform/diff_engine/adapters/cert_adapter.py`
- `config/diff-adapters.yaml`
- `scripts/risk_scorer/context.py`
- `scripts/risk_scorer/models.py`
- `scripts/risk_scorer/dimensions.py`
- `scripts/lv3_cli.py`
- `docs/runbooks/dry-run-semantic-diff-engine.md`
- `docs/adr/0120-dry-run-semantic-diff-engine.md`
- `docs/workstreams/adr-0120-dry-run-diff-engine.md`

## Expected Live Surfaces

- `lv3 run converge-netbox --dry-run` displays a structured diff output showing predicted changed objects before asking for confirmation
- `SemanticDiff.total_changes` is a positive integer for a service that has pending changes
- `SemanticDiff.total_changes == 0` for a service that is already converged and up-to-date
- `SemanticDiff.unknown_count > 0` is logged and shown in the approval prompt when a surface has no adapter

## Verification

- Run `uv run --with pytest --with pyyaml pytest tests/unit/test_diff_engine.py tests/test_risk_scorer.py tests/test_lv3_cli.py tests/test_world_state_client.py -q` → all tests pass
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` → repository data models validate
- Run `lv3 run converge-netbox --dry-run` on the controller with valid Windmill metadata → inspect the structured diff output before any API submission
- Run the same dry-run against a workflow without a configured adapter surface → confirm `unknown_count > 0` is rendered and the mutation-surface score contribution rises to the maximum

## Merge Criteria

- Focused unit and integration tests pass for all 5 initial adapters plus the CLI and risk-scoring integration path
- `SemanticDiff` is embedded in the compiled intent model and optional ledger event path
- The risk scorer (ADR 0116) now consumes real diff-engine counts when available and falls back only when a surface is unsupported or unavailable

## Notes For The Next Assistant

- The initial repository implementation resolves desired Docker state from the image catalog rather than fully rendered Compose templates. If a future workflow needs field-level Compose diffing, extend the Docker adapter instead of bypassing it.
- Firewall and Proxmox VM config diffing remain separate follow-up workstreams. Keep unsupported surfaces explicit by emitting `confidence: unknown` objects rather than inventing optimistic counts.
