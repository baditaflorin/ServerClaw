# Workstream WS-0373: Service Registry Live Apply

- ADR: [ADR 0373](../adr/0373-service-registry-and-derived-defaults.md)
- Title: Service Registry and Derived Defaults
- Status: blocked
- Branch: `codex/ws-0373-live-apply`
- Worktree: `.worktrees/ws-0373-live-apply`
- Owner: `codex`
- Depends On: `adr-0344-single-source-environment-topology`, `adr-0359-declarative-postgresql-client-registry`
- Conflicts With: none
- Shared Surfaces: `inventory/group_vars/all/platform_services.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`, `scripts/validate_service_registry.py`, `docs/adr/0373-service-registry-and-derived-defaults.md`, `docs/runbooks/add-new-service-to-platform.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- validate the latest `origin/main` ADR 0373 codepath from an isolated worktree
- replay the governed production live-apply path for the service-registry pattern
- verify representative current-platform services and automation paths end to end
- leave merge-safe evidence and metadata even though ADR 0407 removed `receipts/` from the default committed surface

## Non-Goals

- re-implementing ADR 0373 from scratch when the code is already merged on `origin/main`
- bumping `VERSION`, editing release sections in `changelog.md`, or changing the top-level `README.md` summary before final integration on `main`
- broad unrelated platform changes outside the service-registry/defaults contract

## Expected Repo Surfaces

- `workstreams/active/ws-0373-live-apply.yaml`
- `docs/workstreams/ws-0373-live-apply.md`
- `docs/adr/0373-service-registry-and-derived-defaults.md`
- `docs/adr/implementation-status/adr-0373.yaml`
- `docs/postmortems/adr-0373-service-registry-adoption-completion.md`
- `docs/runbooks/add-new-service-to-platform.md`
- `inventory/group_vars/all/platform_services.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`
- `scripts/validate_service_registry.py`
- `scripts/validate_repo.sh`
- `tests/test_validate_service_completeness.py`
- `tests/test_ansible_execution_scopes.py`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- the current production converge path can apply latest-main ADR 0373 state without undefined-variable regressions
- representative live services across the current platform still derive conventional defaults correctly from the registry
- repo automation and validation entrypoints that guard ADR 0373 remain green from the isolated worktree

## Verification

- Repo preparation and rebase completed from latest `origin/main` (`ad2280a54`).
- Passed:
  - `python3 scripts/validate_service_registry.py --check`
  - `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validate_service_registry.py tests/test_validate_service_completeness.py tests/test_ansible_execution_scopes.py`
  - `uv run --with pyyaml python scripts/ansible_scope_runner.py validate`
  - `./scripts/run_python_with_packages.sh pyyaml jsonschema -- scripts/service_redundancy.py --validate`
  - `scripts/validate_public_entrypoints.py --check`
  - `./scripts/validate_repo.sh agent-standards`
  - `uv run --with pytest --with pyyaml python -m pytest -q tests/test_interface_contracts.py tests/test_generate_status_docs.py tests/test_canonical_truth.py tests/test_environment_topology.py tests/test_validate_service_registry.py tests/test_validate_service_completeness.py tests/test_ansible_execution_scopes.py`
  - `python3 scripts/interface_contracts.py --list`
  - `make preflight WORKFLOW=live-apply-service`
  - `make check-canonical-truth`
- Current inherited gap:
  - `./scripts/validate_repo.sh data-models` still fails in the local validation harness because the ignored `receipts/live-applies/` archive is incomplete after ADR 0407 and several historical receipt evidence refs still target renamed/removed files. The ADR 0373 codepaths and current catalog validators now pass; the remaining failure is receipt-history drift rather than a live service-registry regression.

## Live Apply Outcome

- blocked on live platform access-path outage after repo-side validation and execution-path fixes

## Live Evidence

- Repo-side ADR 0373 fixes before live replay:
  - `scripts/validate_service_registry.py` now validates current inventory-aware host groups and service-type-specific requirements correctly on latest `origin/main`.
  - `config/ansible-execution-scopes.yaml` now includes the missing scopes required by the current repo validator.
  - `scripts/generate_platform_vars.py` and `scripts/service_redundancy.py` both now avoid the stdlib `platform` import shadowing bug that blocked validation from an isolated worktree.
  - `config/image-catalog.json` placeholder entries for `librechat_runtime` and `litellm_runtime` now use a validator-compatible scaffold state so the image-policy path can be exercised from this branch before final pin/scan.
  - `config/service-redundancy-catalog.json` is back in schema shape and now includes current-main `librechat`, `litellm`, and `neko` entries.
  - `config/health-probe-catalog.json`, `config/workbench-information-architecture.json`, and `config/correction-loops.json` were repaired where current-main drift blocked ADR 0373 validation lanes.
- Additional latest-main governance fixes completed in this turn:
  - `platform/interface_contracts.py` now accepts collection-backed playbook refs, and `config/workflow-catalog.json` now declares the missing top-level playbook wrappers for converge workflows that already run through `Makefile`.
  - `playbooks/services/repo_intake.yml` now matches the standard service-wrapper pattern and imports `playbooks/repo-intake.yml`, allowing the governed scoped runner to plan the service entrypoint instead of rejecting the wrapper's custom Jinja host expression.
  - `docs/workstreams/ws-0377-repo-intake-subdomain.md` restores the missing workstream doc referenced by `workstreams.yaml`, so the workstream-registry contract now validates on latest `origin/main`.
- Governed replay evidence from `2026-04-12`:
  - `make live-apply-service service=repo_intake env=production ALLOW_IN_PLACE_MUTATION=true` now passes preflight, canonical truth, and live-apply contract checks and reaches the scoped Ansible execution for `playbooks/services/repo_intake.yml`.
  - The scoped runner successfully plans `limit=docker-runtime` and starts the live play before failing on first-hop transport during `Gathering Facts`.
  - Local `tailscale status --json` reports `BackendState: Starting` with health `You are logged out. The last login error was: fetch control key: Get "https://headscale.lv3.org/key?v=125": dial tcp 65.108.75.123:443: connect: operation timed out`.
  - Direct reachability checks from this workstation fail consistently:
    - `ssh -i .local/ssh/bootstrap.id_ed25519 ops@100.64.0.1` on ports `22` and `2222` returns `Connection refused`
    - `ssh -i .local/ssh/bootstrap.id_ed25519 ops@65.108.75.123` on ports `22` and `2222` times out
    - `curl -Ik --max-time 15 https://headscale.lv3.org` and `curl -Ik --max-time 15 https://65.108.75.123` both time out
  - Conclusion: the remaining blocker is a live control-plane / host-access outage outside the repo. ADR 0373 repo automation and governed execution surfaces are ready to resume once the Proxmox host and Headscale access path are reachable again.

## Mainline Integration Notes

- protected integration files remain untouched on this branch until the final verified integration step
- the governed replay on latest `origin/main` required a local canonical-truth refresh for `README.md`, `changelog.md`, and `versions/stack.yaml`; those protected-file updates are intentionally not committed on this workstream branch and must be regenerated again before the next live-apply retry
- once host access is restored, rerun `make live-apply-service service=repo_intake env=production ALLOW_IN_PLACE_MUTATION=true`, continue the representative ADR 0373 service replays, and only then update ADR 0373 implementation metadata plus the protected integration files on `main`
