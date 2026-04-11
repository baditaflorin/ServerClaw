# Workstream ws-0191-live-apply: ADR 0191 Live Apply From Latest `origin/main`

- ADR: [ADR 0191](../adr/0191-immutable-guest-replacement-for-stateful-and-edge-services.md)
- Title: guest-level immutable replacement policy, production live-apply guard, and branch-local live verification
- Status: live_applied
- Branch: `codex/ws-0191-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0191-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0182-live-apply-merge-train`
- Conflicts With: none
- Shared Surfaces: `config/immutable-guest-replacement-catalog.json`, `docs/schema/immutable-guest-replacement-catalog.schema.json`, `scripts/immutable_guest_replacement.py`, `scripts/validate_repository_data_models.py`, `scripts/sync_windmill_seed_schedules.py`, `Makefile`, `docs/runbooks/immutable-guest-replacement.md`, `receipts/live-applies/`

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
- `python3 -m py_compile scripts/sync_windmill_seed_schedules.py`
- `make immutable-guest-replacement-plan service=grafana`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grafana`
- `./scripts/validate_repo.sh retry-guard`
- `./scripts/validate_repo.sh agent-standards`
- `make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'`
- `make validate`

## Merge Criteria

- the guest policy catalog stays aligned with inventory and active services
- governed service replays fail closed without the explicit exception flag
- the branch records the production receipt, ADR metadata, and workstream status needed for a later safe merge to `main`

## Outcome

- implementation commits `27804621ae4fef5e7b061e40d284eca1bece88c5` and `b323baa14615cb9bf50af3dad590edb4f5c919fb` added the catalog, schema, guard script, Makefile integration, validation wiring, runbooks, and fresh generated README doc index updates needed for the branch-local live apply path
- `make immutable-guest-replacement-plan service=grafana` resolved the governed production service path as `grafana -> monitoring`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grafana` failed closed with exit code `2` until the documented override was supplied
- `scripts/sync_windmill_seed_schedules.py` was migrated from a raw `time.sleep` retry loop to `platform.retry.with_retry` so the broad validation path could move past the unrelated retry-guard failure
- the bounded production replay `make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'` completed cleanly with `monitoring : ok=176 changed=0 unreachable=0 failed=0 skipped=34`
- `curl -Ik --resolve grafana.example.com:443:203.0.113.1 https://grafana.example.com/d/lv3-platform-overview/lv3-platform-overview` returned `HTTP/2 302` to `/login`, and the local monitoring guest health endpoints for Grafana, Prometheus, Alertmanager, Blackbox Exporter, and Tempo all remained healthy
- the branch records receipt `2026-03-27-adr-0191-immutable-guest-replacement-live-apply` and verifies the production platform change on canonical platform version `0.130.31` from repo version context `0.177.12`
- the workstream merged to `origin/main` on 2026-03-28 in repo version `0.177.13`
- the broad repo gate now reaches repository data model validation, where `make validate` currently stops on the unrelated preexisting `ansible-scope-runner` error `playbook 'playbooks/proxmox-staging-bridge.yml' does not define imports or a leaf catalog entry`

## Post-Merge Notes

- the `main` integration step advanced the repository release metadata to `0.177.13`
- `versions/stack.yaml` intentionally keeps platform version `0.130.31` because no fresh mainline live apply was required to preserve the already-verified branch-local platform state
- a separate follow-up workstream still needs to clear the unrelated broad-gate blocker in `playbooks/proxmox-staging-bridge.yml` so `make validate` can complete end to end from this repo tip
