# Workstream ADR 0078: Service Scaffold Generator

- ADR: [ADR 0078](../adr/0078-service-scaffold-generator.md)
- Title: Collection-native `make scaffold-service` generator for new service docs, roles, playbooks, topology, and catalog contracts
- Status: merged
- Branch: `codex/adr-0078-mainline-rebuild`
- Worktree: `.worktrees/adr-0078-mainline-rebuild`
- Owner: codex
- Depends On: `adr-0062-role-composability`, `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0077-compose-secrets-injection`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `Makefile`, `collections/ansible_collections/lv3/platform/roles/_template/`, `config/`, `inventory/host_vars/proxmox_florin.yml`, `workstreams.yaml`

## Scope

- implement `scripts/scaffold_service.py`
- add `make scaffold-service` and `make pin-image`
- add collection-backed scaffold assets under `collections/ansible_collections/lv3/platform/roles/_template/service_scaffold/`
- generate role, playbook, ADR, workstream, runbook, topology, service, health, subdomain, secret, controller-local-secret, and image catalog surfaces
- add the scaffold placeholder guard to repository data-model validation
- document the operator workflow in `docs/runbooks/scaffold-new-service.md`

## Verification

- `uv run --with pyyaml python -m unittest tests.test_scaffold_service`
- `uv run --with pyyaml --with jsonschema python -m unittest tests.test_validate_service_catalog tests.test_subdomain_catalog`
- disposable repo copy:
  - `make scaffold-service NAME=test-echo ...`
  - `ansible-playbook -i inventory/hosts.yml playbooks/test-echo.yml --syntax-check`
  - `scripts/validate_repository_data_models.py --validate` fails on the intended scaffold `TODO` marker
- repository branch:
  - `make validate`

## Outcome

- repository implementation is complete on `main` in repo release `0.94.0`
- the scaffold generator now targets the collection-based role layout and current catalog schemas instead of the older root-role layout from the original draft
- no live platform version change is claimed; this workstream adds repository-side onboarding automation only
