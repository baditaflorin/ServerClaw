# Workstream ADR 0044: Windmill For Agent And Operator Workflows

- ADR: [ADR 0044](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md)
- Title: On-platform workflow runtime for agents and operators
- Status: live_applied
- Branch: `codex/adr-0044-windmill`
- Worktree: `../proxmox_florin_server-windmill`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `postgres-lv3`, workflow APIs, webhook entry points

## Scope

- choose the workflow runtime for server-side automation
- define how repo-managed scripts become durable scheduled or API-triggered jobs
- constrain how secrets and credentials flow into the runtime

## Non-Goals

- treating the workflow UI as the source of truth instead of git
- introducing secret-bearing repo-managed jobs before ADR 0043 exists

## Expected Repo Surfaces

- `docs/adr/0044-windmill-for-agent-and-operator-workflows.md`
- `docs/workstreams/adr-0044-windmill.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `playbooks/windmill.yml`
- `roles/windmill_postgres/`
- `roles/windmill_runtime/`
- `config/windmill/scripts/lv3-healthcheck.py`
- `workstreams.yaml`

## Expected Live Surfaces

- private Windmill runtime on `docker-runtime-lv3`
- PostgreSQL database `windmill` on `postgres-lv3`
- Tailscale operator entrypoint at `http://100.118.189.95:8005`
- repo-managed workspace `lv3` with seeded script `f/lv3/windmill_healthcheck`

## Verification

- `make syntax-check-windmill`
- `make converge-windmill`
- `curl -s http://100.118.189.95:8005/api/version`
- `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.118.189.95:8005/api/users/whoami`
- `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"probe":"manual-run"}' http://100.118.189.95:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fwindmill_healthcheck`

## Merge Criteria

- the repo-managed Windmill converge path applies cleanly from `main`
- private operator access, workspace bootstrap, and seeded healthcheck execution are verified live

## Notes For The Next Assistant

- keep new Windmill scripts under repo-managed files and sync them through automation
- treat OpenBao integration and narrower Windmill identities as follow-up work, not as reasons to hand-edit secrets into Windmill
- keep secret-bearing workflows constrained until ADR 0043 and ADR 0047 are live
