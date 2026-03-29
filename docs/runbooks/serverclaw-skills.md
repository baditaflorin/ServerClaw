# ServerClaw Skills

## Purpose

ADR 0257 defines the first governed skill-pack contract for ServerClaw.

The current implementation adopts OpenClaw-compatible `SKILL.md` directories and
resolves them with explicit repository-managed precedence:

- workspace-local skill packs override shared skill packs
- shared skill packs override bundled skill packs
- mirrored third-party skill packs stay disabled until they are reviewed and
  promoted into the shared root

## Canonical Sources

- skill catalog: [config/serverclaw/skill-packs.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/skill-packs.yaml)
- approved refs: [config/serverclaw/approved-port-refs.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/approved-port-refs.json)
- bundled skills: [config/serverclaw/skills/bundled](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/skills/bundled)
- shared skills: [config/serverclaw/skills/shared](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/skills/shared)
- workspace skills: [config/serverclaw/workspaces](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/workspaces)
- mirrored imports: [config/serverclaw/skills/imported](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/serverclaw/skills/imported)
- resolver module: [platform/use_cases/serverclaw_skills.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/platform/use_cases/serverclaw_skills.py)
- CLI: [scripts/serverclaw_skill_packs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/scripts/serverclaw_skill_packs.py)
- governed tool: [config/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-openclaw-skills/config/agent-tool-registry.json)

## Directory Contract

Each skill pack is one directory whose name becomes the stable `skill_id`:

```text
config/serverclaw/skills/shared/change-approval/
└── SKILL.md
```

Each `SKILL.md` must start with YAML front matter that includes:

- `name`
- `description`
- optional `metadata.lv3.tool_refs`
- optional `metadata.lv3.connector_refs`
- optional `metadata.lv3.browser_refs`
- optional `metadata.lv3.memory_refs`
- optional `metadata.lv3.search_refs`

The prompt body after the front matter is the committed skill content.

## Primary Commands

Validate the repo-managed skill contract:

```bash
python3 scripts/serverclaw_skill_packs.py --validate
```

Resolve the active skills for the default workspace:

```bash
python3 scripts/serverclaw_skill_packs.py --include-prompt-manifest
```

Resolve one workspace explicitly:

```bash
python3 scripts/serverclaw_skill_packs.py --workspace-id ops --include-prompt-manifest
```

Show one active skill:

```bash
python3 scripts/serverclaw_skill_packs.py --workspace-id ops --skill-id platform-observe
```

Call the governed tool registry surface:

```bash
python3 scripts/agent_tool_registry.py \
  --call list-serverclaw-skills \
  --args-json '{"workspace_id":"ops","include_prompt_manifest":true}'
```

## Operating Rule

When adding or changing ServerClaw skill packs:

1. keep the active skill inside `config/serverclaw/skills/shared/` or `config/serverclaw/workspaces/<workspace>/skills/`
2. keep mirrored third-party packs under `config/serverclaw/skills/imported/` with `enabled: false`
3. reference only governed tool ids or approved port refs
4. rerun `python3 scripts/serverclaw_skill_packs.py --validate`
5. rerun `scripts/agent_tool_registry.py --validate`
6. rerun the focused tests that cover the resolver and any delivery surfaces you changed

Mirrored third-party content is intentionally not an execution path. Review it,
adapt it if needed, and then promote the approved pack into the shared root.
