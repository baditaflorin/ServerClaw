# Workstream ws-0300-live-apply: Live Apply ADR 0300 From Latest `origin/main`

- ADR: [ADR 0300](../adr/0300-falco-for-container-runtime-syscall-security-monitoring-and-autonomous-anomaly-detection.md)
- Title: Implement ADR 0300 by restoring the runtime-control NATS fan-out path and replaying Falco from the latest realistic `origin/main`
- Status: merged
- Included In Repo Version: 0.178.0
- Branch-Local Evidence: `receipts/live-applies/evidence/2026-04-03-ws-0300-smoke-r3-after-nats.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0300-falco-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.96
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Latest-Main Baseline: repo `0.177.153`, platform `0.130.97`
- Workstream Branch: `codex/ws-0300-live-apply`
- Integrated Branch: `main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0300-live-apply`
- Owner: codex
- Depends On: `adr-0052`, `adr-0066`, `adr-0124`, `adr-0276`, `adr-0300`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0300-live-apply.md`, `docs/adr/0300-falco-for-container-runtime-syscall-security-monitoring-and-autonomous-anomaly-detection.md`, `docs/adr/0340-dedicated-coolify-apps-vm-separation.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-falco-runtime.md`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `config/capacity-model.json`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/service-capability-catalog.json`, `config/service-completeness.json`, `config/subdomain-exposure-registry.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `.ansible-lint-ignore`, `.config-locations.yaml`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/matrix_admin_register.py`, `scripts/matrix_bridge_smoke.py`, `scripts/coolify_tool.py`, `config/falco/`, `config/ntfy/server.yml`, `config/ntfy/topics.yaml`, `config/event-taxonomy.yaml`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `playbooks/coolify.yml`, `playbooks/falco.yml`, `playbooks/services/falco.yml`, `playbooks/services/nats-jetstream.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`, `collections/ansible_collections/lv3/platform/roles/nats_jetstream_runtime/`, `collections/ansible_collections/lv3/platform/roles/falco_runtime/`, `collections/ansible_collections/lv3/platform/roles/falco_event_bridge_runtime/`, `collections/ansible_collections/lv3/platform/roles/loki_log_agent/templates/config.alloy.j2`, `scripts/drift_lib.py`, `scripts/falco_event_bridge.py`, `scripts/falco_event_bridge_server.py`, `scripts/nats_streams.py`, `scripts/validate_nats_topics.py`, `tests/test_coolify_tool.py`, `tests/test_docker_runtime_role.py`, `tests/test_falco_event_bridge.py`, `tests/test_falco_runtime_role.py`, `tests/test_nats_jetstream_runtime_role.py`, `tests/test_ntfy_runtime_config.py`, `tests/test_security_posture_report.py`, `tests/unit/test_event_taxonomy.py`, `receipts/live-applies/2026-04-03-adr-0300-falco-mainline-live-apply.json`, `receipts/live-applies/2026-04-03-adr-0340-coolify-apps-vm-separation-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-adr-0300-*`, `receipts/live-applies/evidence/2026-04-03-ws-0300-*`, `receipts/gate-bypasses/*.json`, `receipts/restic-backups/20260403T092200Z.json`, `receipts/restic-snapshots-latest.json`, `receipts/security-reports/20260403T090506Z.json`

## Scope

- implement the repo-managed Falco runtime and private bridge across the four
  governed production guests
- recover the warning-level event path by aiming the bridge and controller-side
  verification helpers at the managed JetStream runtime on `runtime-control`
- replay the live NATS runtime and required streams before the Falco smoke run
- promote the verified result into canonical mainline truth and preserve the
  live-apply evidence for future merges and audits

## Ownership Notes

- this workstream owns ADR 0300 implementation surfaces plus the runtime-control
  NATS recovery needed to make the live warning path real again
- the latest-main replay preserved two real platform behaviors instead of
  hiding them: the nats-jetstream service replay had to restore the governed
  JetStream bus and streams, and the final Falco converge rescued through a
  live Docker nat-chain drift on `docker-runtime`
- the successful service replay also synced the governed restic backup receipts;
  `falco_overrides` remains intentionally inactive in that backup summary
  because no optional source path exists on the runtime host
- the final exact-main merge also carried forward the already-merged
  Label Studio runtime surfaces and the new `scripts/proxmox_tool.py`
  controller helper so the branch truthfully matches the current
  `origin/main` baseline it is promoting

## Latest-Main Live Verification

- after rebasing onto the latest realistic `origin/main`, the workstream reran
  `make live-apply-service service=nats-jetstream env=production`; the final
  replay succeeded on `runtime-control`, the restic post-hook completed,
  and the evidence is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0300-live-apply-nats-jetstream-r4-after-rebase.txt`
- `make apply-nats-streams` then restored the required
  `PLATFORM_EVENTS`, `RAG_DOCUMENT`, and `SECRET_ROTATION` streams before the
  Falco smoke publish replay, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0300-apply-nats-streams-r1.txt`
- `make converge-falco env=production` completed successfully across
  `docker-runtime`, `docker-build`, `monitoring`, and
  `postgres`; the recap preserved
  `docker-runtime : ok=209 changed=7 failed=0 rescued=1`, which captures
  the live recovery through a missing Docker nat `DOCKER` chain on the bridge
  host instead of masking it, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0300-converge-falco-mainline-r5-after-nats.txt`
- the smoke verifier then confirmed all four governed guests in the health,
  trigger, NATS, ntfy, Loki, and mutation-audit results, with bridge source IPs
  `10.10.10.30`, `10.10.10.40`, `10.10.10.50`, and `127.0.0.1`, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0300-smoke-r3-after-nats.json`

## Repository Validation

- the final exact-main focused pytest replay passed with `178 passed in 41.66s`
  across the Falco, Coolify, Label Studio, and Proxmox helper surfaces,
  preserved in
  `receipts/live-applies/evidence/2026-04-03-adr-0300-mainline-pytest-r4.txt`
- `make validate-data-models` and `./scripts/validate_repo.sh workstream-surfaces`
  both passed on the merged `0.178.0` candidate, preserved in
  `receipts/live-applies/evidence/2026-04-03-adr-0300-mainline-validate-data-models-r10.txt`
  and
  `receipts/live-applies/evidence/2026-04-03-adr-0300-mainline-workstream-surfaces-r5.txt`
- `python3 scripts/release_manager.py --dry-run` confirmed the
  `0.177.153 -> 0.178.0` cut, while the full release-manager write correctly
  stopped on unrelated repo-wide readiness blockers under
  `receipts/live-applies/evidence/2026-04-03-adr-0300-mainline-release-manager-r6-0.178.0.txt`;
  the same lower-level canonical-truth and release-note helpers were then
  executed directly to produce the protected `0.178.0` surfaces, preserved in
  `receipts/live-applies/evidence/2026-04-03-adr-0300-mainline-release-lower-level-r1-0.178.0.txt`
- `receipts/security-reports/20260403T090506Z.json` covers
  `runtime-control` and the governed Falco guests with summary status
  `warn` from pre-existing hardening debt, satisfying the vulnerability-budget
  gate for the nats-jetstream replay without claiming those warnings were fixed

## Final Notes

- ADR 0300 is now canonical on `main` at repository version `0.178.0`; the
  live apply first became true at platform version `0.130.96`, while the
  current exact-main platform baseline remains `0.130.97`
- `receipts/live-applies/2026-04-03-adr-0300-falco-mainline-live-apply.json`
  is the canonical proof for this live apply
