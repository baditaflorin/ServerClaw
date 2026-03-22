# Workstream ADR 0044: Windmill For Agent And Operator Workflows

- ADR: [ADR 0044](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md)
- Title: On-platform workflow runtime for agents and operators
- Status: merged
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

- no direct live apply in this integration step
- a ready-to-run Windmill converge path for later controlled rollout

## Verification

- `make syntax-check-windmill`
- `make workflow-info WORKFLOW=converge-windmill`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/lv3-healthcheck.py`

## Merge Criteria

- the repo has a coherent Windmill converge path with documented bootstrap artifacts and seeded script sync
- secret handling and private publication expectations remain explicit

## Notes For The Next Assistant

- keep new Windmill scripts under repo-managed files and sync them through automation
- treat OpenBao integration and narrower Windmill identities as follow-up work, not as reasons to hand-edit secrets into Windmill
- validate the host-side proxy and API path live before changing this workstream back to `live_applied`
