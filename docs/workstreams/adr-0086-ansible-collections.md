# Workstream ADR 0086: Ansible Collection Packaging

- ADR: [ADR 0086](../adr/0086-ansible-collection-packaging.md)
- Title: Restructure 40+ roles into the lv3.platform collection with DRY shared utilities and internal Galaxy server
- Status: ready
- Branch: `codex/adr-0086-ansible-collections`
- Worktree: `../proxmox_florin_server-ansible-collections`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`
- Conflicts With: any workstream branch with roles in `roles/` (coordinate via shared-surface gate)
- Shared Surfaces: `roles/`, `playbooks/`, `ansible.cfg`, `requirements.yml`, `Makefile`

## Scope

- create `collections/lv3/platform/` directory structure with `galaxy.yml`, `roles/`, `plugins/`, `playbooks/`, `meta/`, `molecule/`
- migrate all roles from `roles/` to `collections/lv3/platform/roles/` (mechanical rename + FQCN update)
- extract four shared utility roles: `preflight`, `common_handlers`, `secret_fact`, `wait_for_healthy`
- update all role `meta/main.yml` files to declare dependencies on the shared roles
- update all playbooks to use FQCNs (`lv3.platform.<role_name>`)
- create symlink `roles/` → `collections/lv3/platform/roles/` for backwards compatibility
- provision internal Galaxy server (`galaxy.lv3.org`) as a Compose service on `docker-runtime-lv3`
- write `make collection-build`, `make collection-publish`, `make collection-install` targets
- write Windmill workflow `collection-publish` (triggers on `collections/` changes merged to `main`)
- write `docs/runbooks/ansible-collection-development.md`

## Non-Goals

- writing `molecule` tests for all 40+ roles in this workstream (each role's molecule tests are written separately as roles are worked on)
- publishing the collection to public Ansible Galaxy

## Expected Repo Surfaces

- `collections/lv3/platform/galaxy.yml` (version 1.0.0)
- `collections/lv3/platform/roles/` (all existing roles migrated)
- `collections/lv3/platform/roles/preflight/`, `common_handlers/`, `secret_fact/`, `wait_for_healthy/` (new shared roles)
- `collections/lv3/platform/plugins/filter_plugins/` (extracted Jinja2 filters)
- updated `ansible.cfg` (collections path, Galaxy server config)
- updated `requirements.yml`
- `roles/` symlink
- updated `Makefile` (3 new collection targets)
- Windmill script `config/windmill/scripts/collection-publish.py`
- `docs/runbooks/ansible-collection-development.md`
- `docs/adr/0086-ansible-collection-packaging.md`
- `docs/workstreams/adr-0086-ansible-collections.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `galaxy.lv3.org` serves `lv3.platform:1.0.0`
- `ansible-galaxy collection install lv3.platform:1.0.0 -s internal_galaxy` completes successfully from the controller
- all playbooks pass `ansible-playbook --syntax-check` after migration

## Verification

- `make collection-build` produces `lv3-platform-1.0.0.tar.gz` with all roles present
- `make collection-publish` pushes to `galaxy.lv3.org` and updates the manifest
- `ansible-lint` passes on all playbooks after the FQCN migration
- the `preflight` shared role is referenced in at least 5 roles via `meta/main.yml` (DRY validation)

## Merge Criteria

- all existing playbooks pass `--syntax-check` and `ansible-lint` after migration
- `galaxy.lv3.org` is live and serving `lv3.platform:1.0.0`
- DRY extraction confirmed: duplicate preflight blocks removed from at least 15 roles

## Notes For The Next Assistant

- do the FQCN migration in a single automated pass using `sed` to rewrite role references; then run `ansible-lint` to catch any missed references
- the `common_handlers` role must be a `handlers/` only role (no tasks); include it via `handlers_from` in consumer role `meta/main.yml`
- Galaxy server provisioning: use the `pulp-minimal` Docker image; it only needs the `pulp_ansible` plugin; the full Pulp stack is overkill
