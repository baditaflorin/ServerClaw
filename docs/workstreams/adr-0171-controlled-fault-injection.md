# Workstream ADR 0171: Controlled Fault Injection for Resilience Validation

- ADR: [ADR 0171](../adr/0171-controlled-fault-injection-for-resilience-validation.md)
- Title: Local Windmill fault-injection drills for Keycloak and OpenBao resilience validation
- Status: live_applied
- Implemented In Repo Version: 0.166.0
- Implemented In Platform Version: 0.130.16
- Implemented On: 2026-03-26
- Branch: `codex/adr-0171-fault-injection`
- Worktree: `.worktrees/adr-0171-fault-injection`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0087-validation-gate`
- Conflicts With: none
- Shared Surfaces: `config/fault-scenarios.yaml`, `scripts/fault_injection.py`, `config/windmill/scripts/`, `config/workflow-catalog.json`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `versions/stack.yaml`

## Scope

- add the ADR 0171 fault-injection framework under `platform/faults/`
- define the repo-managed scenario catalog for the first live subset
- seed a Windmill wrapper and scheduled run for the monthly first-Sunday drill
- expose the suite through the workflow catalog and the operator CLI path
- document the operating model and live-apply evidence expectations
- apply the worker-side script live and execute the first controlled drill from `main`

## Non-Goals

- implementing ADR 0164 circuit breakers or ADR 0167 degradation declarations in the same change
- faulting the Proxmox host, physical networking, or external SaaS dependencies
- adding long-running chaos experiments beyond the bounded monthly subset

## Expected Repo Surfaces

- `platform/faults/`
- `scripts/fault_injection.py`
- `config/fault-scenarios.yaml`
- `config/windmill/scripts/fault-injection.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `config/workflow-catalog.json`
- `docs/runbooks/fault-injection.md`
- `docs/adr/0171-controlled-fault-injection-for-resilience-validation.md`
- `docs/workstreams/adr-0171-controlled-fault-injection.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill seeds `f/lv3/fault-injection`
- the first-Sunday guarded schedule exists in the `lv3` workspace
- `.local/fault-injection/latest.json` is written by a live worker run
- the initial live subset completes with the affected containers restored and healthy

## Verification

- `python3 -m py_compile scripts/fault_injection.py config/windmill/scripts/fault-injection.py platform/faults/injector.py`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_fault_injection.py tests/test_fault_injection_repo_surfaces.py tests/test_fault_injection_windmill.py tests/test_windmill_operator_admin_app.py -q`
- `make syntax-check-windmill`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `make fault-injection FAULT_INJECTION_ARGS='scenario_names=fault:keycloak-unavailable,fault:openbao-unavailable'`

## Outcome

- Repository implementation shipped in release `0.166.0` and the first production live apply completed on 2026-03-26 in platform version `0.130.16`.
- The live subset now seeds `f/lv3/fault-injection`, keeps the guarded first-Sunday schedule active in the `lv3` workspace, and writes the latest drill report under `.local/fault-injection/latest.json`.
- Governed production drills passed for both `fault:openbao-unavailable` and `fault:keycloak-unavailable`; OpenBao became unreachable during the bounded pause window and recovered without losing seal state, while Keycloak failed both the private readiness probe and the published discovery probe during the bounded stop/start outage and recovered cleanly.
- The final live rollout needed one documented manual recovery step: after the limited `playbooks/windmill.yml` replay synced the repo checkout but failed later in the unrelated Windmill raw-app export path with `password authentication failed for user "windmill_admin"`, the missing `f/lv3/fault-injection` script was seeded directly through the guest-local Windmill API from `/srv/proxmox_florin_server/config/windmill/scripts/fault-injection.py` before the governed drills were rerun.
