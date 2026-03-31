# Workstream ws-0290-live-apply: Live Apply ADR 0290 From Latest `origin/main`

- ADR: [ADR 0290](../adr/0290-redpanda-as-the-kafka-compatible-streaming-platform.md)
- Title: Deploy Redpanda as the private Kafka-compatible durable streaming platform
- Status: in_progress
- Branch: `codex/ws-0290-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0290-live-apply`
- Owner: codex
- Depends On: `adr-0077`, `adr-0086`, `adr-0153`, `adr-0165`, `adr-0191`, `adr-0276`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0290`, `docs/workstreams/ws-0290-live-apply.md`, `docs/runbooks/configure-redpanda.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `playbooks/redpanda.yml`, `playbooks/services/redpanda.yml`, `collections/ansible_collections/lv3/platform/playbooks/redpanda.yml`, `roles/redpanda_runtime/`, `collections/ansible_collections/lv3/platform/roles/redpanda_runtime/`, `config/*catalog*.json`, `Makefile`, `tests/test_redpanda_playbook.py`, `tests/test_redpanda_runtime_role.py`, `workstreams.yaml`, `receipts/live-applies/`

## Purpose

Implement ADR 0290 by making Redpanda repo-managed on `docker-runtime-lv3`,
preserving controller-local principal credentials through OpenBao, and leaving a
clear live-apply audit trail that another agent can merge safely onto the
protected `main` surfaces.

## Scope

- add the repo-managed Redpanda playbooks, runtime role, and topic smoke contract
- wire Redpanda into the platform topology, execution scopes, and service catalogs
- live-apply the service from this isolated worktree and verify Kafka, HTTP Proxy,
  Schema Registry, and Admin API behaviour end to end
- record branch-local evidence and state so the final merge-to-main step knows
  exactly which protected integration files still need synchronized updates

## Non-Goals

- publishing Redpanda on the public edge
- introducing multi-broker Redpanda clustering or tiered storage
- rewriting protected release files before the final exact-main integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0290-live-apply.md`
- `docs/adr/0290-redpanda-as-the-kafka-compatible-streaming-platform.md`
- `docs/runbooks/configure-redpanda.md`
- `docs/adr/.index.yaml`
- `README.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `playbooks/redpanda.yml`
- `playbooks/services/redpanda.yml`
- `collections/ansible_collections/lv3/platform/playbooks/redpanda.yml`
- `collections/ansible_collections/lv3/platform/roles/redpanda_runtime/`
- `config/ansible-execution-scopes.yaml`
- `config/command-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/secret-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/workflow-catalog.json`
- `Makefile`
- `tests/test_redpanda_playbook.py`
- `tests/test_redpanda_runtime_role.py`
- `receipts/image-scans/2026-03-30-redpanda-runtime.json`
- `receipts/image-scans/2026-03-30-redpanda-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0290-redpanda-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0290-redpanda-live-apply.txt`

## Expected Live Surfaces

- `docker-runtime-lv3` listens privately on `10.10.10.20:9092`, `:9644`,
  `:8097`, and `:8099`
- `/opt/redpanda/docker-compose.yml` exists on `docker-runtime-lv3`
- `lv3-redpanda` and `redpanda-openbao-agent` are running on `docker-runtime-lv3`
- the Redpanda Admin API answers `GET /v1/status/ready`
- the HTTP Proxy accepts a smoke record on `platform.redpanda.smoke`
- the Schema Registry answers for `platform.redpanda.smoke-value`

## Ownership Notes

- `docker-runtime-lv3` is governed by ADR 0191 immutable guest replacement, so
  any in-place replay on this branch must stay a documented narrow exception
- the live mutation must hold the ADR 0153 resource lock for `vm:120/service:redpanda`
- protected release-truth surfaces still wait for the final exact-main
  integration step after live verification succeeds

## Verification So Far

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_redpanda_runtime_role.py tests/test_redpanda_playbook.py` passed before and after the latest-main refresh with `7 passed`
- `make syntax-check-redpanda` passed before and after the latest-main refresh
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py validate` passed
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0290syntax2 --playbook playbooks/services/redpanda.yml --env production -- --private-key .local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check` passed
- `make preflight WORKFLOW=converge-redpanda` passed and confirmed the expected controller-local Redpanda password files will be generated on first converge
- `./scripts/validate_repo.sh generated-vars data-models workstream-surfaces agent-standards health-probes` passed after the `workstreams.yaml` status enum was normalized to `in_progress`
- `uv tool run --from ansible-lint ansible-lint playbooks/redpanda.yml playbooks/services/redpanda.yml collections/ansible_collections/lv3/platform/playbooks/redpanda.yml roles/redpanda_runtime collections/ansible_collections/lv3/platform/roles/redpanda_runtime` passed after the role was hardened away from enterprise-only Schema Registry ACL reconciliation
- `make immutable-guest-replacement-plan service=redpanda` confirmed Redpanda remains governed by ADR 0191 on `docker-runtime-lv3` with `classification=edge_and_stateful`, `validation=preview_guest`, and `rollback=180m`
- `make check-canonical-truth` initially failed because the generated README document index did not yet include the new Redpanda runbook and workstream links; `uvx --from pyyaml python scripts/generate_status_docs.py --write` refreshed only those generated README index entries, not the protected top-level integrated status summary, and `make check-canonical-truth` then passed
- `make live-apply-service service=redpanda env=production` failed closed exactly as ADR 0191 intends, after preflight plus interface, redundancy, and standby checks succeeded, because in-place mutation on `docker-runtime-lv3` still requires the documented narrow exception
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=redpanda env=production EXTRA_ARGS='--syntax-check'` passed end to end through the governed wrapper, proving the exact automation lane through preflight, canonical-truth, interface contracts, standby, redundancy, immutable-guest guard override, and the scoped Ansible syntax path
- Read-only SSH verification on `docker-runtime-lv3` showed the pre-apply baseline still has no `/opt/redpanda`, no listeners on `9092/9644/8097/8099`, and no Redpanda containers running

## Current Blocker

- ADR 0153 lock acquisition for `vm:120/service:redpanda` is currently blocked by an existing exclusive lock on the whole VM: `resource 'vm:120/service:redpanda' is locked by agent:codex/ws-0277-live-apply:vm:120`
- `make resource-locks` at `2026-03-30T13:20Z` showed the conflicting `vm:120` lock held by `agent:codex/ws-0277-live-apply` with expiry `2026-03-30T14:22:24Z`
- Do not run the live Redpanda mutation until that VM-level lock is released or expires without renewal
