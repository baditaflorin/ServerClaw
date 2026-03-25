# Workstream ADR 0171: Controlled Fault Injection for Resilience Validation

- ADR: [ADR 0171](../adr/0171-controlled-fault-injection-for-resilience-validation.md)
- Title: Local Windmill fault-injection drills for Keycloak and OpenBao resilience validation
- Status: in_progress
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

- `make validate`
- `python3 -m pytest tests/test_fault_injection.py tests/test_fault_injection_repo_surfaces.py tests/test_fault_injection_windmill.py tests/test_windmill_operator_admin_app.py -q`
- `make converge-windmill`
- `python3 scripts/lv3_cli.py run fault-injection --approve-risk --args scenario_names=fault:keycloak-unavailable,fault:openbao-unavailable`
