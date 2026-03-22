# Workstream ADR 0063: Centralised Vars And Computed Facts Library

- ADR: [ADR 0063](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0063-centralised-vars-and-computed-facts-library.md)
- Title: Single source of truth for platform facts with agent-queryable output
- Status: ready
- Branch: `codex/adr-0063-platform-vars-library`
- Worktree: `../proxmox_florin_server-platform-vars-library`
- Owner: codex
- Depends On: `adr-0062-role-composability`
- Conflicts With: any workstream that adds new host_vars or group_vars without the new schema
- Shared Surfaces: `inventory/group_vars/`, `versions/stack.yaml`, `filter_plugins/`, `Makefile`

## Scope

- define `inventory/group_vars/platform.yml` as generated from `stack.yaml`
- write `scripts/generate_platform_vars.py` to produce `platform.yml` from `stack.yaml` and `host_vars`
- add `filter_plugins/platform_facts.py` for URL construction helpers
- add `make show-platform-facts` target
- update `make validate` to regenerate and diff `platform.yml` as part of validation
- remove duplicate variable declarations from at least three roles as a proof-of-concept

## Non-Goals

- multi-environment variable layering
- storing secrets in the vars library

## Expected Repo Surfaces

- `inventory/group_vars/platform.yml` (generated)
- `scripts/generate_platform_vars.py`
- `filter_plugins/platform_facts.py`
- updated `Makefile` with `show-platform-facts` and updated `validate` target
- `docs/adr/0063-centralised-vars-and-computed-facts-library.md`
- `docs/workstreams/adr-0063-platform-vars-library.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no live changes; roles use the same variable values, just resolved from one location

## Verification

- `make validate` passes including `platform.yml` consistency check
- `make show-platform-facts` outputs a valid YAML dump without errors
- `python3 scripts/generate_platform_vars.py --dry-run` exits 0

## Merge Criteria

- `platform.yml` is reproducible from `stack.yaml` alone
- the filter plugin is covered by at least one role that uses it
- no duplicate variable declarations remain in the three proof-of-concept roles

## Notes For The Next Assistant

- `platform.yml` must be committed to the repo so agents can read it without running `make`
- mark `platform.yml` as generated in `.gitattributes` to keep diffs clean
