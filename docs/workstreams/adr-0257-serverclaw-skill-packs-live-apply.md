# Workstream ADR 0257: ServerClaw Skill Packs Live Apply

- ADR: [ADR 0257](../adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- Title: Implement the governed ServerClaw `SKILL.md` contract across controller, API gateway, and Windmill from the latest `origin/main`
- Status: in_progress
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

- in progress

## Notes For The Next Assistant

- if the live apply finishes on this branch before merge-to-main, update ADR 0257 metadata and record the exact receipt id here
- protected integration files can wait until the final mainline integration step, but the receipt, workstream doc, and ADR metadata must already say what remains
