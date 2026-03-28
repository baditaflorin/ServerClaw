# Workstream WS-0211: Shared Policy Packs And Rule Registries Live Apply

- ADR: [ADR 0211](../adr/0211-shared-policy-packs-and-rule-registries.md)
- Title: Centralize repeated platform policy rules into one machine-checked registry and replay the governed automation paths from an isolated latest-main worktree
- Status: ready
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0211-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0211-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0180-standby-capacity-reservation-and-placement-rules`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0192-separate-capacity-classes-for-standby-recovery-and-preview-workloads`
- Conflicts With: none
- Shared Surfaces: `config/shared-policy-packs.json`, `docs/schema/shared-policy-packs.schema.json`, `scripts/shared_policy_packs.py`, `scripts/service_redundancy.py`, `scripts/standby_capacity.py`, `scripts/capacity_report.py`, `scripts/failure_domain_policy.py`, `scripts/environment_topology.py`, `scripts/validate_repository_data_models.py`, `docs/runbooks/`, `docs/adr/0211-shared-policy-packs-and-rule-registries.md`, `docs/adr/.index.yaml`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add one machine-checkable shared policy registry for redundancy tiers, capacity classes, and placement policies
- remove hand-edited duplicated rule sets from validators, schemas, and runbooks where the registry should be canonical
- replay the affected repository validation and live-apply automation paths from the isolated worktree
- record merge-safe evidence and any remaining main-only integration work explicitly

## Non-Goals

- changing the underlying redundancy, capacity, or placement decisions themselves
- rewriting unrelated release metadata on the workstream branch
- introducing a broad new policy engine beyond the currently duplicated rule surfaces

## Expected Repo Surfaces

- `config/shared-policy-packs.json`
- `docs/schema/shared-policy-packs.schema.json`
- `scripts/shared_policy_packs.py`
- `scripts/service_redundancy.py`
- `scripts/standby_capacity.py`
- `scripts/capacity_report.py`
- `scripts/failure_domain_policy.py`
- `scripts/environment_topology.py`
- `scripts/validate_repository_data_models.py`
- `docs/schema/service-redundancy-catalog.schema.json`
- `docs/schema/capacity-model.schema.json`
- `docs/schema/environment-topology.schema.json`
- `docs/runbooks/capacity-model.md`
- `docs/runbooks/capacity-classes.md`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/failure-domain-policy.md`
- `tests/test_shared_policy_packs.py`

## Expected Live Surfaces

- the governed `live-apply-service` preflight uses the shared policy registry for redundancy and standby checks
- repository data-model validation consumes the shared policy registry directly
- no hand-edited runtime policy drift remains between the affected repo validators

## Verification

- `uv run --with pytest --with jsonschema --with pyyaml pytest -q tests/test_shared_policy_packs.py tests/test_capacity_report.py tests/test_service_redundancy.py tests/test_standby_capacity.py tests/test_failure_domain_policy.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh data-models generated-docs generated-portals agent-standards`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=homepage env=production EXTRA_ARGS='-e bypass_promotion=true'`

## Outcome

Pending implementation and live verification.
