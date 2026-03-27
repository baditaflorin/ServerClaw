# Ansible Inventory Sharding

## Scope

This runbook covers the repo-managed execution-scope catalog introduced by ADR 0176 and the scoped runner used by mutable Ansible entrypoints.

## Source Of Truth

- scope catalog: `config/ansible-execution-scopes.yaml`
- resolver and shard renderer: `platform/ansible/execution_scopes.py`
- operator-facing CLI wrapper: `scripts/ansible_scope_runner.py`
- integrated entrypoints: `Makefile` live-apply targets and dedicated converge playbooks

## Validate The Catalog

```bash
uvx --from pyyaml python scripts/ansible_scope_runner.py validate
./scripts/validate_repo.sh data-models
```

Validation fails when:

- a mutable leaf playbook lacks catalog metadata
- a wrapper import tree resolves to an uncataloged mutable leaf
- a catalog entry points at a missing file
- a host- or lane-scoped playbook declares an invalid shard class

## Inspect A Planned Run

Use `plan` before changing scope metadata or when checking what `live-apply` will actually target:

```bash
uvx --from pyyaml python scripts/ansible_scope_runner.py plan --playbook playbooks/services/api-gateway.yml --env production
uvx --from pyyaml python scripts/ansible_scope_runner.py plan --playbook playbooks/monitoring-stack.yml --env production
```

The output includes:

- resolved `mutation_scope`
- leaf playbooks under wrapper imports
- concrete target hosts discovered from `ansible-playbook --list-hosts`
- the per-run shard inventory path
- the exact `--limit` expression used for execution

## Run Through The Scoped Path

The normal path is already wired into `Makefile`, but the runner can also be called directly:

```bash
ANSIBLE_HOST_KEY_CHECKING=False \
uvx --from pyyaml python scripts/ansible_scope_runner.py run \
  --playbook playbooks/services/api-gateway.yml \
  --env production \
  -- --syntax-check
```

The runner:

1. resolves the playbook's declared scope metadata
2. expands wrapper imports to the leaf playbooks they carry
3. derives the real host set from `ansible-playbook --list-hosts`
4. writes a run-scoped shard inventory under `.ansible/shards/<run-id>/`
5. executes `ansible-playbook` with that shard inventory plus a matching `--limit`

## Updating Scope Metadata

When a mutable playbook changes target shape:

1. update `config/ansible-execution-scopes.yaml`
2. rerun `plan` for the playbook in each supported environment
3. rerun `uvx --from pyyaml python scripts/ansible_scope_runner.py validate`
4. rerun the focused tests in `tests/test_ansible_execution_scopes.py`

Prefer the narrowest truthful scope:

- `host` for exactly one non-local host
- `lane` only when the play really belongs to one execution lane and declares `target_lane`
- `platform` for cross-host, shared-host, or controller-plus-host mutations
