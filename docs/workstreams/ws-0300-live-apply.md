# Workstream ws-0300-live-apply: Live Apply ADR 0300 From Latest `origin/main`

- ADR: [ADR 0300](../adr/0300-falco-for-container-runtime-syscall-security-monitoring-and-autonomous-anomaly-detection.md)
- Title: Replay the repo-managed Falco runtime and private event bridge from the latest `origin/main` base state
- Status: in_progress
- Implemented In Repo Version: TBD
- Live Applied In Platform Version: TBD
- Implemented On: TBD
- Live Applied On: TBD
- Branch: `codex/ws-0300-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0300-live-apply`
- Owner: codex
- Depends On: `adr-0052`, `adr-0066`, `adr-0124`, `adr-0276`, `adr-0300`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0299`, `docs/adr/0300`, `docs/workstreams/ws-0300-live-apply.md`, `docs/runbooks/configure-falco-runtime.md`, `docs/runbooks/configure-ntfy.md`, `.ansible-lint-ignore`, `.config-locations.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/matrix_admin_register.py`, `scripts/matrix_bridge_smoke.py`, `config/falco/`, `config/ntfy/server.yml`, `config/event-taxonomy.yaml`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `playbooks/falco.yml`, `playbooks/services/falco.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`, `collections/ansible_collections/lv3/platform/roles/falco_runtime/`, `collections/ansible_collections/lv3/platform/roles/falco_event_bridge_runtime/`, `scripts/falco_event_bridge.py`, `scripts/falco_event_bridge_server.py`, `tests/test_docker_runtime_role.py`, `tests/test_falco_runtime_role.py`, `tests/test_ntfy_runtime_config.py`, `receipts/live-applies/`

## Scope

- deploy the private Falco event bridge on `docker-runtime-lv3`
- deploy Falco syscall monitoring on `docker-runtime-lv3`, `docker-build-lv3`, `monitoring-lv3`, and `postgres-lv3`
- route Falco WARNING+ events to NATS and CRITICAL events to ntfy while keeping all JSON events in Loki
- record live-apply evidence, smoke-trigger proof, and any merge-to-main follow-up required for canonical version files

## Non-Goals

- changing the protected top-level `README.md` integrated status summary on this workstream branch
- bumping `VERSION` or editing numbered release sections in `changelog.md` on this workstream branch
- updating `versions/stack.yaml` unless this workstream becomes the final verified main-integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0300-live-apply.md`
- `docs/adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md`
- `docs/adr/0300-falco-for-container-runtime-syscall-security-monitoring-and-autonomous-anomaly-detection.md`
- `docs/runbooks/configure-falco-runtime.md`
- `docs/runbooks/configure-ntfy.md`
- `.ansible-lint-ignore`
- `.config-locations.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `scripts/matrix_admin_register.py`
- `scripts/matrix_bridge_smoke.py`
- `config/falco/`
- `config/ntfy/server.yml`
- `config/event-taxonomy.yaml`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `playbooks/falco.yml`
- `playbooks/services/falco.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`
- `collections/ansible_collections/lv3/platform/roles/falco_runtime/`
- `collections/ansible_collections/lv3/platform/roles/falco_event_bridge_runtime/`
- `scripts/falco_event_bridge.py`
- `scripts/falco_event_bridge_server.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_falco_runtime_role.py`
- `tests/test_ntfy_runtime_config.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `lv3-falco-event-bridge.service` active on `docker-runtime-lv3`
- `falco-modern-bpf.service` active on `docker-runtime-lv3`, `docker-build-lv3`, `monitoring-lv3`, and `postgres-lv3`
- Falco bridge listener reachable on `10.10.10.20:18084` from the other governed guests
- WARNING+ smoke events published to NATS subject `platform.security.falco`
- CRITICAL smoke events published to ntfy topic `platform-security-critical`
- WARNING+ smoke events appended to `/var/log/platform/mutation-audit.jsonl` with `surface="falco"`

## Ownership Notes

- this workstream owns the ADR 0300 runtime implementation and the first live replay evidence from the latest `origin/main` base state
- shared integration files remain deferred until the final verified merge-to-main step unless this same thread performs that integration after the live apply
- the resource-lock set for this replay should cover `vm:120`, `vm:130`, `vm:140`, and `vm:150` before live mutation starts

## Verification Plan

- `make syntax-check-falco`
- targeted pytest for the Falco roles, bridge, event taxonomy, and generated platform vars
- `make validate`
- acquire resource locks for the four touched guests
- `make converge-falco env=production`
- trigger the repo-managed `__lv3_falco_smoke__` marker on each governed guest and record NATS, ntfy, Loki, and mutation-audit evidence

## Current State

- Latest fetched `origin/main` as of `2026-04-03T06:47:00Z` is
  `8e4b9a2164c23f679f1ca9b3c33cacbd6fa06521`, which carries repo version
  `0.177.150`.
- The exact-main replay now carries two additional repository hardening fixes
  beyond the earlier ntfy topic and image compatibility work:
  1. `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
     now accepts either the nftables `DOCKER-FORWARD` chain or the legacy
     filter-table `DOCKER` chain on guests where Docker bridge networking is
     otherwise healthy
  2. `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`
     now force-recreates the ntfy stack with a bounded recovery path for the
     duplicate container-name conflict seen during exact-main handler replay
- Targeted repo validation for the exact-main fixes now passes:
  `26 passed` for `tests/test_docker_runtime_role.py`,
  `tests/test_falco_runtime_role.py`, and
  `tests/test_ntfy_runtime_config.py`, plus
  `make syntax-check-falco` and `make preflight WORKFLOW=converge-falco`.
- Latest exact-main live receipts captured on the branch show:
  1. `receipts/live-applies/evidence/2026-04-03-ws-0300-converge-falco-mainline-r1.txt`
     failed on `docker-build-lv3` because the guest exposed Docker's legacy
     filter-table `DOCKER` chain instead of `DOCKER-FORWARD`
  2. `receipts/live-applies/evidence/2026-04-03-ws-0300-converge-falco-mainline-r2.txt`
     moved past that Docker bridge-chain check and failed later in the ntfy
     restart handler on a duplicate container-name conflict while force-
     recreating the stack
- Targeted branch-local validation cleanup now passes after refreshing
  `build/platform-manifest.json`, regenerating
  `docs/diagrams/agent-coordination-map.excalidraw`, removing the duplicate
  `grist_runtime` key from `config/ansible-role-idempotency.yml`, and expanding
  the ws-0300 surface registry for the helper/test artifacts above.
  Evidence:
  1. `receipts/live-applies/evidence/2026-04-03-ws-0300-platform-manifest-write-r2-0.177.150.txt`
  2. `receipts/live-applies/evidence/2026-04-03-ws-0300-generate-diagrams-r1-0.177.150.txt`
  3. `receipts/live-applies/evidence/2026-04-03-ws-0300-platform-manifest-check-r2-0.177.150.txt`
  4. `receipts/live-applies/evidence/2026-04-03-ws-0300-dependency-graph-checks-r1-0.177.150.txt`
  5. `receipts/live-applies/evidence/2026-04-03-ws-0300-closeout-gates-r2-0.177.150.txt`
  6. `receipts/live-applies/evidence/2026-04-03-ws-0300-ansible-lint-targeted-r1-0.177.150.txt`

## Current Blockers

- `vm:120` cannot be reacquired for a full-VM Falco replay yet because the
  shared lock registry currently holds both `vm:120/service:ops_portal` until
  `2026-04-03T08:44:52Z` and `vm:120/service:api_gateway` until
  `2026-04-03T08:44:52Z`.
- Once that lock window clears, the remaining work is:
  1. reacquire `vm:120`, `vm:130`, `vm:140`, and `vm:150`
  2. rerun `make converge-falco env=production`
  3. rerun the Falco smoke verifier and record NATS, ntfy, Loki, and
     mutation-audit evidence
  4. update ADR 0300 implementation metadata and integrate the protected main
     version files for merge to `main`
