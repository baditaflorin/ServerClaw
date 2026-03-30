# Workstream WS-0293: Temporal Durable Workflow Engine Live Apply

- ADR: [ADR 0293](../adr/0293-temporal-as-the-durable-workflow-and-task-queue-engine.md)
- Title: Live apply Temporal as the durable workflow and task queue engine from latest `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.109
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0293-temporal-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.72
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0293-temporal-main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0293-temporal-main`
- Owner: codex
- Depends On: `adr-0042-postgresql-as-the-shared-relational-database`,
  `adr-0077-compose-secrets-injection-pattern`,
  `adr-0086-backup-and-recovery-for-stateful-services`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0293-live-apply.md`,
  `docs/adr/0293-temporal-as-the-durable-workflow-and-task-queue-engine.md`,
  `docs/adr/.index.yaml`, `docs/runbooks/configure-temporal.md`,
  `playbooks/temporal.yml`, `playbooks/services/temporal.yml`,
  `collections/ansible_collections/lv3/platform/roles/temporal_postgres/`,
  `collections/ansible_collections/lv3/platform/roles/temporal_runtime/`,
  `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`,
  `config/controller-local-secrets.json`, `config/secret-catalog.json`,
  `config/image-catalog.json`, `config/service-capability-catalog.json`,
  `config/health-probe-catalog.json`, `config/service-completeness.json`,
  `config/data-catalog.json`, `config/service-redundancy-catalog.json`,
  `config/dependency-graph.json`, `config/command-catalog.json`,
  `config/workflow-catalog.json`, `config/ansible-execution-scopes.yaml`,
  `config/ansible-role-idempotency.yml`, `Makefile`,
  `scripts/temporal_smoke.py`, `tests/test_temporal_playbook.py`,
  `tests/test_temporal_postgres_role.py`, `tests/test_temporal_runtime_role.py`,
  `tests/test_generate_platform_vars.py`, `tests/test_dependency_graph.py`,
  `receipts/image-scans/`

## Scope

- deploy Temporal on `docker-runtime-lv3` as a private-only durable workflow
  engine with PostgreSQL persistence on `postgres-lv3`
- bootstrap the required Temporal schemas and the default repo-managed `lv3`
  namespace entirely from repo automation
- keep the frontend gRPC, HTTP, and UI listeners loopback-only so the rollout
  avoids unrelated guest-network and edge-publication surfaces already owned by
  concurrent workstreams
- record scan receipts, live-apply evidence, and ADR metadata once the exact
  latest-main replay is verified end to end

## Expected Repo Surfaces

- `docs/adr/0293-temporal-as-the-durable-workflow-and-task-queue-engine.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0293-live-apply.md`
- `docs/runbooks/configure-temporal.md`
- `playbooks/temporal.yml`
- `playbooks/services/temporal.yml`
- `collections/ansible_collections/lv3/platform/roles/temporal_postgres/`
- `collections/ansible_collections/lv3/platform/roles/temporal_runtime/`
- `config/controller-local-secrets.json`
- `config/secret-catalog.json`
- `config/image-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/data-catalog.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `Makefile`
- `scripts/temporal_smoke.py`
- `tests/test_temporal_playbook.py`
- `tests/test_temporal_postgres_role.py`
- `tests/test_temporal_runtime_role.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_dependency_graph.py`
- `receipts/image-scans/2026-03-30-temporal-server-runtime.json`
- `receipts/image-scans/2026-03-30-temporal-server-runtime.trivy.json`
- `receipts/image-scans/2026-03-30-temporal-admin-tools-runtime.json`
- `receipts/image-scans/2026-03-30-temporal-admin-tools-runtime.trivy.json`
- `receipts/image-scans/2026-03-30-temporal-ui-runtime.json`
- `receipts/image-scans/2026-03-30-temporal-ui-runtime.trivy.json`

## Expected Live Surfaces

- Temporal frontend gRPC on `127.0.0.1:7233` and HTTP on `127.0.0.1:7243`
  inside `docker-runtime-lv3`
- Temporal UI on `127.0.0.1:8099` inside `docker-runtime-lv3`
- PostgreSQL databases `temporal` and `temporal_visibility` on `postgres-lv3`
- repo-managed namespace `lv3` with `168h` retention

## Verification Plan

- run the Temporal-focused role and playbook tests plus the shared catalog,
  dependency, command, execution-scope, and completeness validation slices
- run `make syntax-check-temporal`, the image-policy validator, and the repo
  gate path after the workstream registry entry is in place
- replay `make converge-temporal env=production` from this fresh latest-main
  worktree, then verify cluster health, namespace existence, UI reachability,
  and a smoke workflow over an operator tunnel
- update the ADR, workstream registry, and live-apply receipts only after the
  on-platform verification is complete

## Outcome

- The exact-main replay from the integrated `0.177.109` tree succeeded in
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-converge-temporal-0.177.109.txt`
  with final recap `docker-runtime-lv3 ok=174 changed=2 failed=0` and
  `postgres-lv3 ok=59 changed=2 failed=0`.
- Runtime verification is recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-runtime-health.txt`
  and reconfirms the loopback-only Temporal gRPC, HTTP, and UI listeners,
  `SERVING` cluster health, and the repo-managed `lv3` namespace with
  `168h0m0s` retention.
- PostgreSQL headroom is recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-postgres-headroom.txt`
  with `100|71` active sessions at observation time and `temporal|9`,
  confirming the ADR 0293 guardrails avoided the earlier saturation state.
- The remote smoke workflow is recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-temporal-smoke-remote.json`
  with `elapsed_ms: 371` and result message `temporal-smoke:lv3`.
- The merged-tree repository automation path is recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-remote-validate-0.177.109.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0293-mainline-pre-push-gate-0.177.109.txt`;
  every substantive lane passed, and the only non-pass was the expected
  `workstream-surfaces` guard because `codex/ws-0293-mainline-replay` is the
  temporary exact-main replay branch rather than a terminal workstream branch
  registered in `workstreams.yaml`.
- The final mainline replay also hardened the Temporal namespace retention
  reconciliation path so repeated exact-main runs now retry cleanly during
  admin-tools startup and skip unnecessary namespace updates when the declared
  `168h` retention is already present.
