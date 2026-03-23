# Workstream ADR 0120: Dry-Run Semantic Diff Engine

- ADR: [ADR 0120](../adr/0120-dry-run-semantic-diff-engine.md)
- Title: CPU-only preflight engine that computes a structured SemanticDiff for any ExecutionIntent before execution — predicts exact changed objects across Ansible, OpenTofu, Docker, DNS, TLS, and firewall surfaces
- Status: ready
- Branch: `codex/adr-0120-diff-engine`
- Worktree: `../proxmox_florin_server-diff-engine`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0085-opentofu-vm-lifecycle`, `adr-0090-platform-cli`, `adr-0112-goal-compiler`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`
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
- update `platform/goal_compiler/compiler.py` — call `DiffEngine.compute()` after compilation; embed `SemanticDiff` in the compiled intent display
- update `lv3 run` CLI display — render `SemanticDiff` as the structured change summary before the approval prompt
- write `tests/unit/test_diff_engine.py` — test each adapter independently with fixture data; test `unknown` confidence propagation; test empty diff

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
- `platform/goal_compiler/compiler.py` (patched: diff engine call added)
- `docs/adr/0120-dry-run-semantic-diff-engine.md`
- `docs/workstreams/adr-0120-diff-engine.md`

## Expected Live Surfaces

- `lv3 run "deploy netbox" --dry-run` displays a structured diff output showing predicted changed objects before asking for confirmation
- `SemanticDiff.total_changes` is a positive integer for a service that has pending changes
- `SemanticDiff.total_changes == 0` for a service that is already converged and up-to-date
- `SemanticDiff.unknown_count > 0` is logged and shown in the approval prompt when a surface has no adapter

## Verification

- Run `pytest tests/unit/test_diff_engine.py -v` → all tests pass
- Run `lv3 run "deploy netbox" --dry-run` on the controller → inspect the structured diff output
- Run `lv3 run "deploy netbox" --dry-run` a second time immediately after a successful deployment → confirm `total_changes == 0`
- Introduce an intentional config drift (manually edit a netbox config file on the server) → run `--dry-run` again → confirm the drift appears as a predicted change

## Merge Criteria

- Unit tests pass for all 5 initial adapters
- End-to-end dry-run tested for at least 2 services (netbox and one other)
- Zero-change detection verified
- `SemanticDiff` embedded in compiled intent ledger event
- Risk scorer (ADR 0116) `expected_change_count` stub replaced with real diff engine output

## Notes For The Next Assistant

- The Ansible adapter's 60-second subprocess timeout may be too short for playbooks that target many hosts. Make the timeout configurable per adapter in `config/diff-adapters.yaml` with a default of 90 seconds.
- `ansible-playbook --check --diff` requires a reachable inventory. On the controller, the inventory is at `inventory/` in the repo. The adapter must resolve the inventory path relative to the repo root, not the CWD of the calling process.
- The Docker adapter compares desired state (parsed from `docker-compose.yml`) against current state (Docker API). "Desired state" must be computed from the compose file after template rendering (if using Jinja2 templates in compose files). Render with the same variable sources used by the Ansible playbook.
- Treat all `confidence: unknown` objects as requiring operator review; surface them prominently in the CLI output with a `? unknown:` prefix rather than burying them in the change list.
