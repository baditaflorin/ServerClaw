# Workstream ws-0191-live-apply: ADR 0191 Live Apply From Latest `origin/main`

- ADR: [ADR 0191](../adr/0191-immutable-guest-replacement-for-stateful-and-edge-services.md)
- Title: guest-level immutable replacement policy, production live-apply guard, and branch-local live verification
- Status: implemented
- Branch: `codex/ws-0191-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0191-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0182-live-apply-merge-train`
- Conflicts With: none
- Shared Surfaces: `config/immutable-guest-replacement-catalog.json`, `docs/schema/immutable-guest-replacement-catalog.schema.json`, `scripts/immutable_guest_replacement.py`, `scripts/validate_repository_data_models.py`, `Makefile`, `docs/runbooks/immutable-guest-replacement.md`, `receipts/live-applies/`

## Scope

- add a machine-readable guest policy catalog for ADR 0191
- validate the catalog against inventory, service ownership, and redundancy tiers
- expose an operator planner for governed services and guests
- make the production service live-apply path require an explicit exception before in-place mutation continues on a governed guest
- replay one bounded production service converge from the worktree with the documented narrow exception and record the verification evidence

## Non-Goals

- building a full guest replacement controller in this workstream
- changing protected integration files on the branch
- claiming a new canonical platform version before merge-to-`main`

## Expected Repo Surfaces

- `config/immutable-guest-replacement-catalog.json`
- `docs/schema/immutable-guest-replacement-catalog.schema.json`
- `scripts/immutable_guest_replacement.py`
- `tests/test_immutable_guest_replacement.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `.config-locations.yaml`
- `docs/runbooks/immutable-guest-replacement.md`
- `docs/runbooks/deploy-a-service.md`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/adr/0191-immutable-guest-replacement-for-stateful-and-edge-services.md`
- `docs/workstreams/ws-0191-live-apply.md`

## Expected Live Surfaces

- the production `live-apply-service` path blocks governed services unless the operator explicitly acknowledges the narrow in-place exception
- the new planner can resolve the live production policy for at least one governed service from the branch worktree
- one bounded production converge replays successfully with `ALLOW_IN_PLACE_MUTATION=true` and matching verification evidence

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_immutable_guest_replacement.py tests/test_service_redundancy.py tests/test_live_apply_receipts.py`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 -m py_compile scripts/immutable_guest_replacement.py scripts/validate_repository_data_models.py`
- `make immutable-guest-replacement-plan service=grafana`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grafana`
- `make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'`

## Merge Criteria

- the guest policy catalog stays aligned with inventory and active services
- governed service replays fail closed without the explicit exception flag
- the branch records the production receipt, ADR metadata, and workstream status needed for a later safe merge to `main`

## Outcome

- pending live apply

## Remaining For Merge To `main`

- protected integration files still need the normal mainline release step after this workstream is reviewed and merged
