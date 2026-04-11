# Workstream ws-0361-live-apply: ADR 0361 Semaphore Keycloak OIDC Integration

- ADR: [ADR 0361](../adr/0361-semaphore-keycloak-oidc-integration.md)
- Title: verify and live-apply the repo-managed Semaphore Keycloak OIDC flow from the latest origin/main
- Status: blocked
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-11-adr-0361-semaphore-keycloak-oidc-live-apply.json`
- Evidence Summary: `receipts/live-applies/evidence/2026-04-11-ws-0361-summary.txt`
- Mainline Receipt: pending
- Implemented On: 2026-04-11
- Live Applied On: not yet
- Live Applied In Platform Version: not yet applied
- Original Branch Base: `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- Latest Upstream Checked: `origin/main@59fbe662b57c28388e47e784c29f457ffd4ec1d3`
- Branch: `codex/ws-0361-live-apply`
- Worktree: `.worktrees/ws-0361-live-apply`
- Owner: codex
- Depends On: `ADR 0056`, `ADR 0149`, `ADR 0165`, `ADR 0167`, `ADR 0361`
- Conflicts With: none

## Scope

- move Semaphore from a controller-generated OIDC secret to a dedicated repo-managed Keycloak client secret mirrored under `.local/keycloak/`
- converge the Keycloak client before the Semaphore runtime so the controller always consumes the live Keycloak secret contract
- update the Semaphore runbooks, service catalogs, workstream state, and postmortem follow-up so the rotated-secret workflow is clear and reproducible
- verify the repo automation path and the live Semaphore converge from the latest exact-main base

## Outcome So Far

- dedicated worktree and branch created from `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- Semaphore and Keycloak role wiring now reconciles the dedicated Keycloak client before the Semaphore runtime and consumes the mirrored secret from `.local/keycloak/semaphore-client-secret.txt`
- the service catalogs, dependency graph, runbooks, active workstream record, and sanitized historical `ws-0362` note now describe the same repo-managed OIDC boundary
- while this workstream was in flight, `origin/main` advanced to `59fbe662b57c28388e47e784c29f457ffd4ec1d3` with release-only and unrelated Docker/Postgres changes; no overlapping ws-0361 surfaces moved upstream

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_semaphore_runtime_role.py tests/test_semaphore_playbook.py tests/test_keycloak_runtime_role.py` passed with `32 passed in 3.19s`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_dependency_graph.py tests/test_preflight_controller_local.py tests/test_validate_service_completeness.py tests/test_secret_rotation.py` reported `25 passed, 1 failed`; the lone failure is unrelated current-mainline drift in `tests/test_dependency_graph.py` because `litellm` is now a direct hard dependency of `postgres` but the baseline assertion set has not been updated
- `make syntax-check-semaphore` passed
- `make preflight WORKFLOW=converge-semaphore` passed after creating the unrelated ignored artifact directories that the current global workflow catalog expects in a fresh worktree; the preflight correctly reported `keycloak_semaphore_client_secret` as absent-before-apply
- `./scripts/validate_repo.sh workstream-surfaces` passed
- broader repo validators on the same base still report unrelated mainline drift outside ws-0361, including the protected `README.md` public-entrypoint lint, a stale removed `playbooks/jupyterhub.yml` reference in repository data-model validation, and an unrelated `librechat` uptime contract issue

## Live-Apply Blocker

- `make converge-semaphore env=production` reached the scoped Ansible run and then failed before guest work began because SSH to `proxmox-host` at `100.64.0.1:22` timed out
- direct follow-up probes from this workstation also failed:
  - `ssh ops@100.64.0.1`: timeout
  - `ssh ops@65.108.75.123`: timeout
  - `ssh ops@100.118.189.95`: connection refused
  - `ssh -p 2222 ops@100.118.189.95`: connection refused
  - `tailscale ping 100.64.0.1`: timeout
  - `tailscale ping 10.10.10.92`: timeout
  - `ssh ops@10.10.10.92`: timeout
  - `curl http://100.64.0.1:8020/api/ping`: timeout
  - `curl http://100.118.189.95:8020/api/ping`: connection refused
  - `curl https://100.64.0.1:8006/api2/json/`: timeout
- `tailscale status --json` still listed the peer `proxmox-florin-subnet-router` online at `100.64.0.1`, but the local client reported coordination-server health warnings and no viable host or routed-guest management path from this workstation
- `tailscale ssh` could not be used as a fallback because the macOS App Store/TestFlight build installed on this machine does not provide that subcommand
- the current controller-local Semaphore auth artifact still points at `http://100.64.0.1:8020`, so the repo changes are ready but the live platform state was not mutated from this session

## Remaining Closeout

- restore working reachability to `proxmox-host` or provide the correct `LV3_PROXMOX_HOST_ADDR` for this workstation
- rerun `make converge-semaphore env=production`
- verify `/api/ping`, `/auth/oidc/login`, `make semaphore-manage ACTION=list-projects`, and the seeded `Semaphore Self-Test` template against the live controller
- record the final live-apply receipt(s), update ADR 0361 from `Partial` to `Live applied`, and only then perform the exact-main integration step for protected release surfaces

## Notes

- protected integration files stay intentionally untouched on this workstream branch because the live apply did not complete: no `VERSION` bump, no release-section edits in `changelog.md`, no top-level `README.md` status rewrite, and no `versions/stack.yaml` update
