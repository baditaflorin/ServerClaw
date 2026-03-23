# Workstream ADR 0065: Secret Rotation Automation With OpenBao

- ADR: [ADR 0065](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0065-secret-rotation-automation-with-openbao.md)
- Title: Bounded credential lifetimes with automated rotation via OpenBao and Windmill
- Status: live_applied
- Branch: `codex/adr-0065-secret-rotation`
- Worktree: `../proxmox_florin_server-secret-rotation`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0044-windmill`, `adr-0047-short-lived-creds`, `adr-0048-command-catalog`
- Conflicts With: none
- Shared Surfaces: OpenBao KV, `config/`, Windmill workflows, NATS events, GlitchTip

## Scope

- define `config/secret-catalog.json` schema and populate with current static secrets
- create Windmill workflow `rotate-credentials` with low-risk auto-rotation and high-risk approval gate
- add `tasks/rotate.yml` to each service role that holds a rotatable credential
- wire rotation events to NATS `credentials.rotated` and GlitchTip on failure
- document the rotation model in `docs/runbooks/secret-rotation-and-lifecycle.md`

## Non-Goals

- rotating SSH host keys or Proxmox root passwords (break-glass scope)
- rotating ephemeral OpenBao dynamic leases (those have their own TTL)

## Expected Repo Surfaces

- `config/secret-catalog.json`
- `docs/runbooks/secret-rotation-and-lifecycle.md`
- `tasks/rotate.yml` in postgres, mail platform, and windmill roles
- Windmill workflow definition (committed to `roles/windmill/files/workflows/`)
- `docs/adr/0065-secret-rotation-automation-with-openbao.md`
- `docs/workstreams/adr-0065-secret-rotation-automation.md`
- `workstreams.yaml`

## Expected Live Surfaces

- OpenBao KV entries for each managed static secret with rotation metadata
- a running scheduled Windmill workflow with daily execution
- NATS subscription for rotation events

## Verification

- `python3 -c "import json; json.load(open('config/secret-catalog.json'))"` exits 0
- Windmill workflow definition passes syntax check
- rotation dry-run completes without error against the test credential

## Merge Criteria

- the rotation model and approval gate behaviour are documented clearly
- the first rotation has been performed manually as a dry-run receipt
- no plaintext secrets appear in any committed file

## Notes For The Next Assistant

- start with the postgres service password as the lowest-risk rotation candidate
- the approval gate for high-risk rotations reuses the command-catalog approval mechanism from ADR 0048

## Repo Implementation Notes

- Repo implementation completed on `2026-03-23` for release `0.73.0`.
- Live apply completed on `2026-03-23` for platform version `0.36.0`.
- The first successful live rotation covered `windmill_database_password`, including controller-local secret mirroring, Windmill runtime restart, and OpenBao metadata updates.
