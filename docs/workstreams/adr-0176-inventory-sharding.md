# Workstream ADR 0176: Inventory Sharding And Host-Scoped Ansible Execution

- ADR: [ADR 0176](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0176-inventory-sharding-and-host-scoped-ansible-execution.md)
- Title: Repo-managed Ansible execution scopes, shard inventories, and host-limited live apply
- Status: live_applied
- Branch: `codex/adr-0176-inventory-sharding`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0176-inventory-sharding`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0154-vm-scoped-parallel-execution-lanes`, `adr-0157-per-vm-concurrency-budget`
- Conflicts With: none
- Shared Surfaces: `config/ansible-execution-scopes.yaml`, `platform/ansible/execution_scopes.py`, `scripts/ansible_scope_runner.py`, `Makefile`, `scripts/validate_repo.sh`, `docs/runbooks/ansible-inventory-sharding.md`, `docs/adr/0176-inventory-sharding-and-host-scoped-ansible-execution.md`, `workstreams.yaml`

## Scope

- define the machine-readable catalog for mutable Ansible leaf playbooks
- resolve wrapper imports so `live-apply-service`, `live-apply-group`, and `site` inherit shard metadata without duplicate declarations
- derive concrete target hosts from `ansible-playbook --list-hosts`
- render per-run shard inventories and execute with matching `--limit`
- validate scope coverage from the repo gate and document the operator workflow

## Non-Goals

- implementing dependency-wave planning from ADR 0178 in the same branch
- changing scheduler lock semantics or resource budgets directly
- claiming a production live apply before ADR 0176 is replayed from `main`

## Expected Repo Surfaces

- `config/ansible-execution-scopes.yaml`
- `platform/ansible/execution_scopes.py`
- `scripts/ansible_scope_runner.py`
- `tests/test_ansible_execution_scopes.py`
- `Makefile`
- `scripts/validate_repo.sh`
- `docs/runbooks/ansible-inventory-sharding.md`
- `docs/adr/0176-inventory-sharding-and-host-scoped-ansible-execution.md`
- `docs/workstreams/adr-0176-inventory-sharding.md`
- `workstreams.yaml`

## Expected Live Surfaces

- the merged-main `live-apply-service` path renders a run-scoped shard inventory under `.ansible/shards/<run-id>/`
- host-scoped replays execute with a matching `--limit` while preserving the full repo-relative inventory context required by shared host vars
- the first synchronized production replay evidence is the `ollama` converge recorded in `receipts/live-applies/2026-03-27-adr-0176-inventory-sharding-mainline-live-apply.json`

## Verification

- `uvx --from pyyaml python scripts/ansible_scope_runner.py validate`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_ansible_execution_scopes.py tests/test_platform_manifest.py -q`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from pyyaml python scripts/ansible_scope_runner.py run --playbook playbooks/services/api-gateway.yml --env production -- --syntax-check`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from pyyaml python scripts/ansible_scope_runner.py run --playbook playbooks/monitoring-stack.yml --env production -- --syntax-check`
- `./scripts/validate_repo.sh data-models`

## Merge Criteria

- every mutable live-apply leaf playbook has declared execution-scope metadata
- wrapper playbooks inherit leaf scope metadata without duplicate target-host declarations
- the runner writes a real shard inventory and replays Ansible successfully with a matching `--limit`
- the repository gate rejects scope-catalog drift before merge

## Outcome

- repository implementation merged on `main` in repo release `0.177.0`
- the first fully synchronized `main` replay advanced platform version to `0.130.25` on 2026-03-27 from origin/main commit `f076a89c`
- `make live-apply-service service=ollama env=production` completed with `docker-runtime-lv3 : ok=90 changed=1 unreachable=0 failed=0 skipped=19`
- the final scope plan for run `e78ee2968d0140deba22cec891c50baf` rendered `.ansible/shards/e78ee2968d0140deba22cec891c50baf/ollama-production.json` with `limit_expression` `docker-runtime-lv3`
- the post-apply verification returned `{"version":"0.18.2"}` and showed `0.0.0.0:11434->11434/tcp, [::]:11434->11434/tcp` published for the `ollama` container

## Notes For The Next Assistant

- The synchronized-main replay surfaced and fixed two broader integration regressions outside the ADR 0176 core: ADR 0177 namespaced Ansible SSH control sockets were too long on macOS, and the Ollama runtime needed explicit Docker nat-chain plus host-port recovery after replaying Docker and guest-firewall roles together.
- If a later branch adds true lane-scoped playbooks, extend `config/ansible-execution-scopes.yaml` with `mutation_scope: lane` plus `target_lane`; the resolver and validator already support that class.
