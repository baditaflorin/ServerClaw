# Workstream ADR 0149: Semaphore For Ansible Job Management UI And API

- ADR: [ADR 0149](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0149-semaphore-for-ansible-job-management-ui-and-api.md)
- Title: Private Semaphore runtime for bounded Ansible job execution
- Status: in_progress
- Branch: `codex/adr-0149-semaphore`
- Worktree: `../proxmox_florin_server-adr-0149`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`, `adr-0026-postgres-vm`, `adr-0048-command-catalog`, `adr-0077-compose-runtime-secrets-injection`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `postgres-lv3`, Proxmox host Tailscale proxy, controller-local auth artifacts

## Scope

- deploy Semaphore privately on `docker-runtime-lv3` with a PostgreSQL backend on `postgres-lv3`
- publish the UI and API only on the management tailnet
- seed a repo-managed project, inventory, and self-test template so jobs can be launched through the UI and API on day one
- expose a governed controller wrapper for project listing, template runs, and task-output retrieval

## Non-Goals

- treating Semaphore as the new source of truth for infrastructure design
- promising broad platform self-management from inside Semaphore before internal inventory and secret boundaries are explicitly designed
- exposing Semaphore on the public nginx edge

## Expected Repo Surfaces

- `docs/adr/0149-semaphore-for-ansible-job-management-ui-and-api.md`
- `docs/workstreams/adr-0149-semaphore.md`
- `docs/runbooks/configure-semaphore.md`
- `playbooks/semaphore.yml`
- `playbooks/semaphore-self.yml`
- `roles/semaphore_postgres/`
- `roles/semaphore_runtime/`
- `scripts/semaphore_bootstrap.py`
- `scripts/semaphore_tool.py`
- `platform/ansible/semaphore.py`
- `workstreams.yaml`

## Expected Live Surfaces

- a private Semaphore UI and API on `docker-runtime-lv3`
- a Proxmox-host Tailscale proxy entrypoint at `http://100.64.0.1:8020`
- controller-local Semaphore auth artifacts under `.local/semaphore/`
- a seeded `LV3 Semaphore` project with the `Semaphore Self-Test` template

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `make syntax-check-semaphore`
- `python3 -m py_compile platform/ansible/semaphore.py scripts/semaphore_bootstrap.py scripts/semaphore_tool.py`
- `pytest -q tests/test_semaphore_client.py`
- `make converge-semaphore`
- `curl -fsS http://100.64.0.1:8020/api/ping`
- `make semaphore-manage ACTION=list-projects`
- `make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'`

## Merge Criteria

- the ADR is explicit about private-only publication, initial bootstrap scope, and the boundary between repo truth and UI-run jobs
- the repo-managed Semaphore converge path applies cleanly from `main`
- private access, controller-local auth artifacts, and the seeded Ansible self-test are verified live

## Notes For The Next Assistant

- Repo implementation is complete on `codex/adr-0149-semaphore` after rebasing onto current `origin/main` and revalidating the merged catalogs, generated vars, and supporting docs.
- Live apply remains blocked from this workstation as of 2026-03-25: `make converge-semaphore` now fails immediately with `ssh: connect to host 100.64.0.1 port 22: Connection refused`, while direct SSH to `65.108.75.123` currently returns `No route to host` and the Proxmox API on `:8006` is unreachable on both addresses.
- if a later workstream wants Semaphore to run broader platform converges, design that around an explicit internal inventory, dedicated SSH credential scope, and documented `.local` secret mirroring rather than silently reusing controller assumptions
