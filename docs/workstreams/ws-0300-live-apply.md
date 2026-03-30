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
- Shared Surfaces: `docs/adr/0300`, `docs/workstreams/ws-0300-live-apply.md`, `docs/runbooks/configure-falco-runtime.md`, `docs/runbooks/configure-ntfy.md`, `.ansible-lint-ignore`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/matrix_admin_register.py`, `scripts/matrix_bridge_smoke.py`, `config/falco/`, `config/ntfy/server.yml`, `config/event-taxonomy.yaml`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/ansible-execution-scopes.yaml`, `playbooks/falco.yml`, `playbooks/services/falco.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`, `roles/falco_runtime`, `roles/falco_event_bridge_runtime`, `scripts/falco_event_bridge.py`, `scripts/falco_event_bridge_server.py`, `receipts/live-applies/`

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
- CRITICAL smoke events published to ntfy topic `platform.security.critical`
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

- Rebasing onto the latest `origin/main` completed successfully on `2026-03-30`.
- Targeted validation now passes on the rebased branch:
  `45 passed` for `tests/test_falco_event_bridge.py`,
  `tests/test_falco_runtime_role.py`, `tests/test_generate_platform_vars.py`,
  and `tests/unit/test_event_taxonomy.py`; `make syntax-check-falco`,
  `python3 scripts/workflow_catalog.py --validate`,
  `python3 scripts/command_catalog.py --validate`, and
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  also pass.
- The repo-wide validation replay uncovered rebased-mainline automation debt
  outside the original Falco surfaces. This workstream now also carries the
  minimal validation hygiene needed to keep the latest-main base green:
  OpenBao Jinja spacing in
  `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`,
  the known `complexity[tasks]` allowance in `.ansible-lint-ignore`, and
  retry-policy migrations in `scripts/matrix_admin_register.py` plus
  `scripts/matrix_bridge_smoke.py`.
- The full four-guest lock set was acquired on `2026-03-30` for `vm:120`,
  `vm:130`, `vm:140`, and `vm:150`, so live mutation can proceed immediately
  after the repo-wide validation rerun returns clean.

## Current Blockers

- None beyond the work still in flight: the repo-wide validation rerun,
  `make converge-falco env=production`, smoke evidence capture, and final
  protected-file integration on `main`.
