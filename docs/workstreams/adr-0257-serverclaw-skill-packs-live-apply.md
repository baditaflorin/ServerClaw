# Workstream ADR 0257: ServerClaw Skill Packs Live Apply

- ADR: [ADR 0257](../adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- Title: Implement the governed ServerClaw `SKILL.md` contract across controller, API gateway, and Windmill from the latest `origin/main`
- Status: live_applied
- Implemented In Repo Version: 0.177.117
- Live Applied In Platform Version: 0.130.76
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0257-openclaw-skills-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills`
- Owner: codex
- Depends On: `adr-0069-agent-tool-registry`, `adr-0156-agent-session-workspace-isolation`, `adr-0228-windmill-default-operations-surface`, `adr-0254-serverclaw-product-surface`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md`, `docs/workstreams/adr-0257-serverclaw-skill-packs-live-apply.md`, `docs/adr/.index.yaml`, `docs/runbooks/serverclaw-skills.md`, `docs/runbooks/agent-tool-registry.md`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/windmill-default-operations-surface.md`, `config/agent-tool-registry.json`, `config/serverclaw/`, `platform/use_cases/serverclaw_skills.py`, `scripts/serverclaw_skill_packs.py`, `scripts/agent_tool_registry.py`, `scripts/validate_repository_data_models.py`, `config/windmill/scripts/serverclaw-skills.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `tests/test_serverclaw_skill_packs.py`, `tests/test_serverclaw_skills_windmill.py`, `tests/test_agent_tool_registry.py`, `tests/test_windmill_default_operations_surface.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- implement one repo-managed ServerClaw skill-pack resolver that honors bundled, shared, and workspace-local precedence
- keep mirrored third-party packs disabled until they are explicitly promoted into the governed shared root
- expose the same contract through the controller CLI, the governed tool registry, and a seeded Windmill wrapper
- replay the live API gateway and Windmill converges from the isolated worktree and verify the new surfaces end to end

## Non-Goals

- deploying the full ServerClaw chat runtime
- enabling unreviewed third-party skills directly from mirrored import roots
- granting shell, arbitrary network, or uncontrolled secret access through skill-pack metadata

## Expected Repo Surfaces

- `config/serverclaw/skill-packs.yaml`
- `config/serverclaw/approved-port-refs.json`
- `config/serverclaw/skills/`
- `config/serverclaw/workspaces/`
- `platform/use_cases/serverclaw_skills.py`
- `scripts/serverclaw_skill_packs.py`
- `config/agent-tool-registry.json`
- `scripts/agent_tool_registry.py`
- `scripts/validate_repository_data_models.py`
- `config/windmill/scripts/serverclaw-skills.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/serverclaw-skills.md`
- `docs/runbooks/agent-tool-registry.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-default-operations-surface.md`
- `docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md`
- `docs/workstreams/adr-0257-serverclaw-skill-packs-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- the API gateway Dify tool bridge exposes the new governed `list-serverclaw-skills` tool on `docker-runtime-lv3`
- the Windmill workspace `lv3` gains the seeded `f/lv3/serverclaw_skills` wrapper on `docker-runtime-lv3`
- repo-managed controller validation paths can resolve the same skill-pack catalog without requiring a live shell mutation path

## Verification

- `python3 scripts/serverclaw_skill_packs.py --validate`
- `python3 scripts/agent_tool_registry.py --validate`
- `uv run --with pytest --with pyyaml pytest tests/test_serverclaw_skill_packs.py tests/test_serverclaw_skills_windmill.py tests/test_agent_tool_registry.py tests/test_windmill_default_operations_surface.py -q`
- `make validate-data-models`
- `./scripts/validate_repo.sh agent-standards`
- live replay of `make converge-api-gateway` and `make converge-windmill`
- direct gateway and Windmill checks from the documented Proxmox jump path

## Merge Criteria

- the active skill list is deterministic and proves workspace-local overrides shared and bundled packs
- mirrored third-party packs remain visible for review but disabled for activation
- the controller, gateway, and Windmill surfaces all return the same governed skill-pack resolution
- the branch records the live-apply evidence clearly enough for final integration onto `main`

## Outcome

- live apply completed from the latest realistic `origin/main` baseline and the
  durable proof set is recorded in
  `receipts/live-applies/2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply.json`
- the governed skill-pack contract now resolves consistently through the
  controller CLI, the tool registry, the public API gateway surface, and the
  seeded Windmill wrapper for the `ops` workspace
- the exact-main replay also captured and fixed one adjacent runtime blocker:
  transient OpenBao `500/502/503` reads during restart windows now retry long
  enough for the rotatable-secret verification path to settle on
  `docker-runtime-lv3`

## Live Apply Outcome

- The latest-main replay ran against `origin/main` commit `0b86b8ac4e2c868bab2b489ecff1e44a3913a10c`
  with repo version context `0.177.116`, platform version context `0.130.75`,
  and final runtime-tree source commit `808b924df84dd7fdfd3f3871b5cfe1225b6b22a4`.
- `make converge-api-gateway` succeeded with evidence log
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-api-gateway-r14-0.177.116.txt`,
  and the public `list-serverclaw-skills` proof returned HTTP `200` together
  with the expected workspace-local `platform-observe` override in
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-api-gateway-list-serverclaw-skills-r7-0.177.116.json`.
- The exact-main replay re-established adjacent certificate/runtime
  dependencies: `step-ca` health returned `{"status":"ok"}` in
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-step-ca-health-r2-0.177.116.txt`,
  and the stabilized OpenBao replay completed with recap
  `docker-runtime-lv3 ok=176 changed=9 failed=0`, `postgres-lv3 ok=49 changed=2 failed=0`
  in
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-openbao-r20-0.177.116.txt`.
- `make converge-windmill` completed cleanly with recap
  `docker-runtime-lv3 ok=328 changed=54 failed=0`,
  `postgres-lv3 ok=72 changed=0 failed=0`,
  `proxmox_florin ok=41 changed=4 failed=0`
  in
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-windmill-r27-0.177.116.txt`.
- The seeded Windmill wrapper proof in
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-windmill-serverclaw-skills-r4-0.177.116.json`
  returned the same two active skills as the controller and gateway proofs,
  including the `ops` workspace-local `platform-observe` override shadowing the
  bundled pack.
- Focused repository validation passed on the exact-main branch: the targeted
  ADR 0257 pytest slice passed (`52 passed`), the OpenBao role regression slice
  passed (`19 passed`), `make syntax-check-windmill`,
  `make syntax-check-api-gateway`, `./scripts/validate_repo.sh agent-standards`,
  and `scripts/validate_repository_data_models.py --validate` all passed.

## Live Apply Evidence

- Receipt: `receipts/live-applies/2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply.json`
- Controller proof:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-controller-skill-packs-r7-0.177.116.json`
- Tool registry proof:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-tool-registry-list-serverclaw-skills-r7-0.177.116.json`
- API gateway converge:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-api-gateway-r14-0.177.116.txt`
- Public API proof:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-api-gateway-list-serverclaw-skills-r7-0.177.116.json`
- OpenBao converge:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-openbao-r20-0.177.116.txt`
- Windmill converge:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-converge-windmill-r27-0.177.116.txt`
- Windmill direct proof:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-windmill-serverclaw-skills-r4-0.177.116.json`
- Step-ca health proof:
  `receipts/live-applies/evidence/2026-03-31-adr-0257-mainline-step-ca-health-r2-0.177.116.txt`

## Mainline Integration Outcome

- Release `0.177.117` was cut on 2026-03-31 from the merged mainline publish
  worktree.
- ADR 0257 metadata, `VERSION`, `changelog.md`, `README.md`,
  `docs/release-notes/`, `versions/stack.yaml`, and the generated canonical
  truth surfaces now record this live apply as integrated mainline truth.
- `versions/stack.yaml.live_apply_evidence.latest_receipts.serverclaw_skills`
  now points at
  `2026-03-31-adr-0257-serverclaw-skill-packs-mainline-live-apply`, and the
  integrated platform version advanced to `0.130.76`.
