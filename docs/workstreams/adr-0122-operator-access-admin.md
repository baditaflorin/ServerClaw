# Workstream ADR 0122: Windmill Operator Access Admin Surface

- ADR: [ADR 0122](../adr/0122-windmill-operator-access-admin.md)
- Title: Repo-managed Windmill raw app for browser-first operator onboarding, off-boarding, reconciliation, and inventory
- Status: ready
- Branch: `codex/adr-0122-operator-admin-ui`
- Worktree: `.worktrees/adr-0122-operator-admin-ui`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0066-audit-log`, `adr-0108-operator-onboarding`
- Conflicts With: none
- Shared Surfaces: `config/windmill/scripts/`, `config/windmill/apps/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/operator-onboarding.md`

## Scope

- add ADR 0122 documenting the browser-first operator admin surface on top of ADR 0108
- create `config/windmill/apps/wmill.yaml` for repo-managed Windmill app sync metadata
- create raw app `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`
- add backend runnables for roster listing, operator onboarding, operator off-boarding, reconciliation, and inventory lookup
- add worker-side Windmill wrapper scripts for roster and inventory lookup
- seed the existing operator workflow wrappers into the Windmill workspace from `windmill_runtime`
- extend `windmill_runtime` so it can sync repo-managed raw apps, not only scripts and schedules
- document the new non-terminal admin path in dedicated and related runbooks
- add tests for the app bundle, wrapper scripts, and Windmill role seed metadata

## Non-Goals

- exposing operator creation in the public ops portal
- replacing ADR 0108 CLI entrypoints
- implementing self-service account requests
- changing Keycloak role/group semantics

## Expected Repo Surfaces

- `config/windmill/apps/wmill.yaml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`
- `config/windmill/scripts/operator-roster.py`
- `config/windmill/scripts/operator-inventory.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/meta/argument_specs.yml`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/adr/0122-windmill-operator-access-admin.md`
- `docs/workstreams/adr-0122-operator-access-admin.md`

## Expected Live Surfaces

- Windmill workspace `lv3` contains the app `f/lv3/operator_access_admin`
- the app can list operators from the repo checkout on the worker
- onboarding through the app returns the bootstrap password once and records the normal ADR 0108 audit outputs
- off-boarding through the app calls the same governed backend as the CLI path

## Verification

- Run `uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q`
- Run `python3 -m py_compile config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py`
- Run `ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check`
- Run a TypeScript check for the raw app bundle in a temporary copy with `npm install` and `npx tsc --noEmit`

## Merge Criteria

- Windmill runtime seeds both the operator workflow scripts and the raw app bundle
- the raw app can onboard, off-board, reconcile, and inspect operators through the governed backend wrappers
- runbooks clearly document the browser-first path
- tests cover seed metadata, wrapper behavior, and raw app repo structure

## Delivered

- added ADR 0122 plus a dedicated runbook for the Windmill operator access admin surface
- added worker-side Windmill wrappers for roster and inventory lookup
- added the repo-managed raw app bundle under `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`
- extended `windmill_runtime` to seed the existing operator workflow wrappers and push repo-managed raw apps with the Windmill CLI
- added focused tests for the new app bundle, wrapper scripts, and Windmill seed metadata
