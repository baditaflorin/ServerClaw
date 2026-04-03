# Workstream ws-0325-live-apply: Live Apply ADR 0325 From Latest `origin/main`

- ADR: [ADR 0325](../adr/0325-faceted-adr-index-shards-and-reservation-windows.md)
- Title: Live apply faceted ADR index shards and reservation windows from the latest `origin/main`
- Status: in_progress
- Branch: `codex/ws-0325-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0325-live-apply`
- Owner: codex
- Depends On: `adr-0164`, `adr-0167`, `adr-0168`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0325-live-apply.md`, `docs/adr/0325-faceted-adr-index-shards-and-reservation-windows.md`, `docs/adr/.index.yaml`, `docs/adr/index/`, `docs/runbooks/adr-discovery-and-reservations.md`, `.repo-structure.yaml`, `.config-locations.yaml`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `scripts/adr_discovery.py`, `scripts/generate_adr_index.py`, `scripts/adr_query_tool.py`, `scripts/validate_repo.sh`, `tests/test_generate_adr_index.py`, `tests/test_adr_query_tool.py`, `tests/test_validation_lanes.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Implement ADR 0325 from the latest practical `origin/main` baseline by
switching ADR discovery to compact shard-backed metadata, adding an explicit ADR
number reservation ledger, and proving the repo-managed query, validation, and
allocation paths end to end.

## Scope

- generate a compact `docs/adr/.index.yaml` root manifest plus range, concern,
  and implementation-status shards under `docs/adr/index/`
- add `docs/adr/index/reservations.yaml` and reservation-aware ADR allocation
  tooling
- update repo validation so ADR metadata and reservation changes fail cleanly
  when the generated shard surfaces drift
- document the operational workflow for querying ADRs, reserving windows, and
  refreshing the generated discovery metadata
- preserve live-apply evidence and branch-local verification so another agent
  can merge or replay safely if `origin/main` moves again

## Non-Goals

- rewriting unrelated ADR content outside the 0325 implementation metadata
- inventing speculative future ADR reservations that are not grounded in an
  actual workstream
- updating protected release or canonical-truth surfaces on this workstream
  branch before the exact-main integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0325-live-apply.md`
- `docs/adr/0325-faceted-adr-index-shards-and-reservation-windows.md`
- `docs/adr/.index.yaml`
- `docs/adr/index/`
- `docs/runbooks/adr-discovery-and-reservations.md`
- `.repo-structure.yaml`
- `.config-locations.yaml`
- `config/validation-gate.json`
- `config/validation-lanes.yaml`
- `scripts/adr_discovery.py`
- `scripts/generate_adr_index.py`
- `scripts/adr_query_tool.py`
- `scripts/validate_repo.sh`
- `tests/test_generate_adr_index.py`
- `tests/test_adr_query_tool.py`
- `tests/test_validation_lanes.py`
- `receipts/live-applies/`
- `receipts/live-applies/evidence/`

## Expected Live Surfaces

- `docs/adr/.index.yaml` becomes a compact ADR discovery root manifest instead
  of embedding the full ADR corpus inline
- `docs/adr/index/by-range/`, `by-concern/`, and `by-status/` expose focused
  ADR metadata shards that can be read without loading the entire corpus
- `python3 scripts/adr_query_tool.py allocate` respects committed ADRs plus
  active reservations from `docs/adr/index/reservations.yaml`
- `documentation-index` and `agent-standards` both catch stale ADR discovery
  outputs after ADR or reservation changes

## Verification

- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `python3 scripts/adr_query_tool.py list --concern documentation`
- `python3 scripts/adr_query_tool.py allocate --window-size 2`
- `uv run --with pytest --with pyyaml pytest -q tests/test_generate_adr_index.py tests/test_adr_query_tool.py tests/test_validation_lanes.py`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards`
