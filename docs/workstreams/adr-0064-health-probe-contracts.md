# Workstream ADR 0064: Health Probe Contracts For All Services

- ADR: [ADR 0064](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0064-health-probe-contracts-for-all-services.md)
- Title: Standardised liveness and readiness probes per service with machine-readable catalog
- Status: merged
- Branch: `codex/adr-0064-health-probe-contracts`
- Worktree: `../proxmox_florin_server-health-probe-contracts`
- Owner: codex
- Depends On: `adr-0027-uptime-kuma`, `adr-0062-role-composability`
- Conflicts With: none
- Shared Surfaces: all service roles, `config/`, `config/uptime-kuma/`, `Makefile`

## Scope

- define probe contract format and document it in `docs/runbooks/health-probe-contracts.md`
- create `config/health-probe-catalog.json` with liveness/readiness entries for all current services
- add `tasks/verify.yml` to each current service role, including the newer NetBox, Open WebUI, Portainer, and ntopng roles alongside the original scope
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
- `test -f roles/nginx_edge_publication/tasks/verify.yml`

## Merge Criteria

- every currently-live service has an entry in `health-probe-catalog.json`
- probe contracts are documented in the runbook with example outputs
- the role verify contracts are enforced by the repo validation gate and exercised by the changed playbook syntax checks

## Notes For The Next Assistant

- merged on `main` as repository release `0.59.0`; no live platform apply has happened yet
- host-provided surfaces without standalone roles (`proxmox_ui`, `docker_build`) are covered in the catalog and Uptime Kuma policy, not via new role verify files
