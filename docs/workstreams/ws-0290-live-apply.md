# Workstream ws-0290-live-apply: Live Apply ADR 0290 From Latest `origin/main`

- ADR: [ADR 0290](../adr/0290-redpanda-as-the-kafka-compatible-streaming-platform.md)
- Title: Deploy Redpanda as the private Kafka-compatible durable streaming platform
- Status: live_applied
- Included In Repo Version: 0.177.116
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0290-redpanda-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Release Date: 2026-03-31
- Branch: `codex/ws-0290-mainline`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0290-mainline`
- Owner: codex
- Depends On: `adr-0077`, `adr-0086`, `adr-0153`, `adr-0165`, `adr-0191`, `adr-0276`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0290`, `docs/workstreams/ws-0290-live-apply.md`, `docs/runbooks/configure-redpanda.md`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `playbooks/redpanda.yml`, `playbooks/services/redpanda.yml`, `collections/ansible_collections/lv3/platform/playbooks/redpanda.yml`, `roles/redpanda_runtime/`, `collections/ansible_collections/lv3/platform/roles/redpanda_runtime/`, `config/*catalog*.json`, `config/ansible-role-idempotency.yml`, `Makefile`, `tests/test_ansible_role_idempotency.py`, `tests/test_generate_platform_vars.py`, `tests/test_redpanda_playbook.py`, `tests/test_redpanda_runtime_role.py`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.116.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/ops-portal-snapshot.html`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- add the repo-managed Redpanda runtime, topic reconciliation contract, and
  private Kafka/Admin/HTTP Proxy/Schema Registry topology on
  `docker-runtime`
- replay the governed live-apply path from the latest realistic `origin/main`
  baseline after cutting release `0.177.114`
- verify the service end to end from the exact-main tree and leave a canonical
  receipt plus repo-automation evidence on the branch that was promoted to main

## Non-Goals

- publishing Redpanda on the public edge
- introducing multi-broker Redpanda clustering or tiered storage

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0290-live-apply.md`
- `docs/adr/0290-redpanda-as-the-kafka-compatible-streaming-platform.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-redpanda.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.116.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `inventory/host_vars/proxmox-host.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `playbooks/redpanda.yml`
- `playbooks/services/redpanda.yml`
- `collections/ansible_collections/lv3/platform/playbooks/redpanda.yml`
- `collections/ansible_collections/lv3/platform/roles/redpanda_runtime/`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
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
- `tests/test_ansible_role_idempotency.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_redpanda_playbook.py`
- `tests/test_redpanda_runtime_role.py`
- `receipts/image-scans/2026-03-30-redpanda-runtime.json`
- `receipts/image-scans/2026-03-30-redpanda-runtime.trivy.json`
- `receipts/live-applies/2026-03-31-adr-0290-redpanda-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-*`

## Expected Live Surfaces

- `docker-runtime` listens privately on `10.10.10.20:9092`, `:9644`,
  `:8103`, and `:8104`
- `/opt/redpanda/docker-compose.yml` exists on `docker-runtime`
- `lv3-redpanda` and `redpanda-openbao-agent` are running on `docker-runtime`
- the Redpanda Admin API answers `GET /v1/status/ready`
- the HTTP Proxy accepts a smoke record on `platform.redpanda.smoke`
- the Schema Registry answers for `platform.redpanda.smoke-value`

## Verification

- The exact-main release preparation is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-status-r1.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-dry-run-r1.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-write-r1.txt`;
  the write step prepared repo version `0.177.114` and platform version
  `0.130.75` from the latest realistic `origin/main` baseline.
- The protected mainline integration is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-status-r2-0.177.116.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-dry-run-r2-0.177.116.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-release-write-r2-0.177.116.txt`;
  the write step promoted the verified Redpanda change onto `main` as repo
  version `0.177.116` while keeping platform version `0.130.75`.
- The governed exact-main Redpanda replay from committed source
  `aafea88c9bee78e14372f40b94bc62d3abb79433` is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-live-apply-r1-0.177.114.txt`
  and completed with final recap
  `docker-runtime : ok=176 changed=4 unreachable=0 failed=0 skipped=49 rescued=0 ignored=0`.
- Runtime health evidence is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-runtime-health-r1.json`
  and confirms `GET /v1/status/ready` returned `200`, HTTP Proxy produce and
  readback succeeded with the smoke marker present, Schema Registry returned
  the declared subject, the `lv3-redpanda` and `redpanda-openbao-agent`
  containers were healthy, listeners were bound on `9092`, `9644`, `8103`,
  and `8104`, and both `platform.redpanda.smoke` plus
  `platform.redpanda.smoke.dlq` existed.
- The focused regression slice passed in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-targeted-checks-r2-0.177.114.txt`
  with `47 passed`, and the dedicated syntax lane remains green in
  `receipts/live-applies/evidence/2026-03-31-ws-0290-mainline-syntax-check-r1-0.177.114.txt`.
- The exact-main validation bundle initially exposed two repo-only follow-ups
  outside the Redpanda runtime itself: `config/ansible-role-idempotency.yml`
  was missing `redpanda_runtime`, and the workstream ownership change left the
  generated dependency graph stale. The branch now carries the idempotency
  policy repair, the explicit `tests/test_ansible_role_idempotency.py`
  coverage, the expanded workstream ownership manifest, and refreshed generated
  surfaces.
- Repository automation is now green from the exact-main branch tip:
  `make check-build-server` passed,
  `make remote-validate` passed every selected blocking lane,
  and `make pre-push-gate` passed every blocking check including
  `documentation-index`, `yaml-lint`, `generated-docs`,
  `generated-portals`, `ansible-syntax`, `ansible-lint`, `type-check`,
  `security-scan`, `semgrep-sast`, `packer-validate`, `tofu-validate`, and
  `integration-tests`.

## Outcome

- ADR 0290 first became true in exact-main repo version `0.177.114` and is integrated on `main` in repo version `0.177.116`.
- Redpanda first became true on platform version `0.130.75`.
- `receipts/live-applies/2026-03-31-adr-0290-redpanda-mainline-live-apply.json`
  is the canonical proof for the exact-main Redpanda replay that backed the
  protected mainline integration.
