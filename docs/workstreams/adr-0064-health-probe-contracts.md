# Workstream ADR 0064: Health Probe Contracts For All Services

- ADR: [ADR 0064](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0064-health-probe-contracts-for-all-services.md)
- Title: Standardised liveness and readiness probes per service with machine-readable catalog
- Status: ready
- Branch: `codex/adr-0064-health-probe-contracts`
- Worktree: `../proxmox_florin_server-health-probe-contracts`
- Owner: codex
- Depends On: `adr-0027-uptime-kuma`, `adr-0062-role-composability`
- Conflicts With: none
- Shared Surfaces: all service roles, `config/`, `config/uptime-kuma/`, `Makefile`

## Scope

- define probe contract format and document it in `docs/runbooks/health-probe-contracts.md`
- create `config/health-probe-catalog.json` with liveness/readiness entries for all current services
- add `tasks/verify.yml` to each service role (nginx, docker-runtime, postgres, monitoring, backup, step-ca, openbao, windmill, mail platform)
- add `make validate` syntax check for `verify.yml` presence in service roles
- update Uptime Kuma config stubs in `config/uptime-kuma/` to match catalog entries

## Non-Goals

- SLA definitions or alert thresholds (those live in Grafana)
- full integration test suites

## Expected Repo Surfaces

- `config/health-probe-catalog.json`
- `docs/runbooks/health-probe-contracts.md`
- `tasks/verify.yml` in each service role
- updated `scripts/validate_repo.sh`
- `docs/adr/0064-health-probe-contracts-for-all-services.md`
- `docs/workstreams/adr-0064-health-probe-contracts.md`
- `workstreams.yaml`

## Expected Live Surfaces

- convergence runs for each service role will execute `verify.yml` and fail loudly if the service is unhealthy
- Uptime Kuma monitors updated to match probe catalog

## Verification

- `python3 -c "import json; json.load(open('config/health-probe-catalog.json'))"` exits 0
- `make validate` passes with probe presence check active
- `test -f roles/nginx/tasks/verify.yml`

## Merge Criteria

- every currently-live service has an entry in `health-probe-catalog.json`
- probe contracts are documented in the runbook with example outputs
- at least one service role's `verify.yml` is tested in the worktree environment

## Notes For The Next Assistant

- begin with services that already have HTTP endpoints (nginx, Grafana, Uptime Kuma) before tackling TCP-only services
- the `wait_port.yml` shared task from ADR 0062 is the building block for TCP probes
