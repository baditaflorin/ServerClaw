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
- Shared Surfaces: `docs/adr/0299`, `docs/adr/0300`, `docs/workstreams/ws-0300-live-apply.md`, `docs/runbooks/configure-falco-runtime.md`, `docs/runbooks/configure-ntfy.md`, `.ansible-lint-ignore`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/matrix_admin_register.py`, `scripts/matrix_bridge_smoke.py`, `config/falco/`, `config/ntfy/server.yml`, `config/event-taxonomy.yaml`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/ansible-execution-scopes.yaml`, `playbooks/falco.yml`, `playbooks/services/falco.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`, `roles/falco_runtime`, `roles/falco_event_bridge_runtime`, `scripts/falco_event_bridge.py`, `scripts/falco_event_bridge_server.py`, `receipts/live-applies/`

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
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`
- `collections/ansible_collections/lv3/platform/roles/falco_runtime/`
- `collections/ansible_collections/lv3/platform/roles/falco_event_bridge_runtime/`
- `scripts/falco_event_bridge.py`
- `scripts/falco_event_bridge_server.py`
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

- Latest fetched `origin/main` as of `2026-04-02T11:06:50Z` is
  `cf255eeca51d0b6c1e65ce19a5924d55ed2ed7a4`, which carries repo version
  `0.177.140`.
- The branch now carries three repo-managed ntfy hardening changes required to
  finish ADR 0300 live apply safely:
  1. the k6 warning topic was changed from the rejected dotted slug
     `platform.slo.warn` to the live-compatible hyphenated slug
     `platform-slo-warn`
  2. the ntfy image pin was raised from `binwiederhier/ntfy:v2.14.0` to
     `binwiederhier/ntfy:v2.21.0` so the repo-managed runtime matches the live
     schema already present under `/var/lib/ntfy`
  3. the ntfy role now reasserts Docker bridge chains and retries compose
     startup when Docker reports `Unable to enable DNAT rule` or a missing
     chain during container recreation
- Targeted repo validation for those changes now passes:
  `25 passed` for `tests/test_falco_runtime_role.py` and
  `tests/test_k6_load_testing.py`, plus `make syntax-check-ntfy` and
  `make syntax-check-falco`.
- Live receipts captured on the branch show:
  1. `receipts/live-applies/evidence/2026-04-02-ws-0300-converge-falco-r2.txt`
     successfully replayed Falco after the ntfy topic slug fix
  2. `receipts/live-applies/evidence/2026-04-02-ws-0300-smoke-r1.json`
     proved the remaining end-to-end gaps were NATS and ntfy delivery
  3. `receipts/live-applies/evidence/2026-04-02-ws-0300-nats-jetstream-direct-r1.txt`
     restored the repo-managed NATS runtime when the workflow wrapper was gated
     by protected-file policy
  4. `receipts/live-applies/evidence/2026-04-02-ws-0300-converge-falco-r3.txt`
     failed because the repo-managed ntfy image was older than the live schema
  5. `receipts/live-applies/evidence/2026-04-02-ws-0300-converge-falco-r4.txt`
     moved past the ntfy schema check and exposed the missing Docker
     bridge-chain recovery path that is now implemented in the ntfy role
- Current observed live state on `docker-runtime-lv3` after that recovery work:
  Docker is `active`, the ntfy container is running on
  `0.0.0.0:2586 -> 2586/tcp`, and `curl http://127.0.0.1:2586/v1/health`
  returns `{"healthy":true}`.

## Current Blockers

- `vm:120` cannot be reacquired for a full-VM Falco replay yet because the
  shared lock registry currently holds both `vm:120/service:ops_portal` until
  `2026-04-02T13:03:30Z` and `vm:120/service:api_gateway` until
  `2026-04-02T13:05:20Z`.
- Once that lock window clears, the remaining work is:
  1. reacquire `vm:120`, `vm:130`, `vm:140`, and `vm:150`
  2. rerun `make converge-falco env=production`
  3. rerun the Falco smoke verifier and record NATS, ntfy, Loki, and
     mutation-audit evidence
  4. update ADR 0300 implementation metadata and integrate the protected main
     version files for merge to `main`
