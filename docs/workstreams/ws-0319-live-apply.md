# Workstream ws-0319-live-apply: Apply ADR 0319 And ADR 0320 On Latest `origin/main`

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md)
- Title: Live apply the first runtime-ai pool split with Nomad, Traefik, and Dapr from the latest mainline
- Status: live_applied
- Included In Repo Version: `0.177.142`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply.json`
- Live Applied In Platform Version: `0.130.89`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Branch: `codex/ws-0319-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0319-main-integration`
- Owner: codex
- Depends On: `adr-0232-nomad-for-durable-batch-and-long-running-internal-jobs`, `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0319-live-apply.md`, `docs/adr/0319-runtime-pools-as-the-service-partition-boundary.md`, `docs/adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-runtime-ai-pool.md`, `docs/runbooks/configure-gotenberg.md`, `docs/runbooks/configure-tika.md`, `docs/runbooks/configure-tesseract-ocr.md`, `docs/runbooks/configure-nomad.md`, `inventory/hosts.yml`, `inventory/group_vars/all.yml`, `inventory/group_vars/platform.yml`, `inventory/host_vars/proxmox_florin.yml`, `playbooks/runtime-ai-pool.yml`, `playbooks/services/runtime-ai-pool.yml`, `playbooks/gotenberg.yml`, `playbooks/nomad.yml`, `collections/ansible_collections/lv3/platform/playbooks/tika.yml`, `collections/ansible_collections/lv3/platform/playbooks/tesseract-ocr.yml`, `collections/ansible_collections/lv3/platform/roles/runtime_pool_substrate/`, `collections/ansible_collections/lv3/platform/roles/nomad_namespace/`, `config/execution-lanes.yaml`, `config/ansible-execution-scopes.yaml`, `config/api-gateway-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/slo-catalog.json`, `config/service-redundancy-catalog.json`, `config/workflow-catalog.json`, `config/prometheus/file_sd/slo_targets.yml`, `config/uptime-kuma/monitors.json`, `config/capacity-model.json`, `config/contracts/runtime-pools/runtime-ai/`, `tests/test_runtime_ai_pool_playbook.py`, `tests/test_runtime_pool_substrate_role.py`, `tests/test_generate_platform_vars.py`, `tests/test_gotenberg_runtime_role.py`, `tests/test_tika_playbook.py`, `tests/test_tika_runtime_role.py`, `tests/test_tesseract_ocr_runtime_role.py`, `tests/test_nomad_playbook.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Implement the first live runtime-pool split from the latest exact mainline by
creating `runtime-ai-lv3`, giving it its own execution lane and deployment
surface, reusing Nomad plus Traefik plus Dapr instead of new bespoke runtime
glue, and moving the document-extraction slice off the overloaded shared
runtime VM.

## Scope

- provision the dedicated `runtime-ai-lv3` guest on Proxmox with the declared
  static network identity, memory envelope, and anti-affinity metadata
- enroll `runtime-ai-lv3` as a Nomad client and create the `runtime-ai`
  namespace on the existing scheduler
- stand up the private Traefik router and Dapr invocation bridge on the new
  guest as the first runtime-pool substrate
- migrate Apache Tika, Gotenberg, and Tesseract OCR to `runtime-ai-lv3`
- retire the legacy copies from `docker-runtime-lv3` and keep the authenticated
  `/v1/gotenberg` API gateway path working
- record live-apply evidence and promote the main-only release truth surfaces
  after the exact-main replay succeeds

## Non-Goals

- implementing ADR 0321, ADR 0322, or ADR 0323 in the same workstream
- moving every AI-adjacent workload onto `runtime-ai-lv3` in one cut
- replacing the shared API gateway host in the same rollout

## Verification Plan

- targeted pytest for the updated Tika, Gotenberg, Tesseract OCR, Nomad, and
  generated platform-vars contracts plus the new runtime-ai pool playbook and
  substrate role
- `./scripts/validate_repo.sh agent-standards` before the live apply
- guarded production `live-apply-service` replay for `runtime-ai-pool`
- end-to-end verification of the new guest, Traefik and Dapr substrate, Nomad
  namespace and client registration, migrated service health, legacy service
  retirement, and the authenticated `/v1/gotenberg` gateway route
- final exact-main validation, receipt validation, canonical-truth check, and
  protected release update only after the live platform state is verified

## Outcome

- The first exact-main release cut wrote `0.177.141` on the integration branch before the post-write Outline sync failed with `502 Bad Gateway`; after ADR 0316 occupied `0.177.141` on `origin/main`, this live-applied workstream was integrated as repository release `0.177.142`, and the original external publication failure remains preserved in `receipts/live-applies/evidence/2026-04-02-ws-0319-mainline-release-manager-r2.txt`.
- Governed exact-main replay `receipts/live-applies/evidence/2026-04-02-ws-0319-mainline-live-apply-r2.txt` completed successfully on top of the refreshed mainline with final recap `docker-runtime-lv3 : ok=269 changed=144 failed=0`, `monitoring-lv3 : ok=38 changed=0 failed=0`, `proxmox_florin : ok=41 changed=8 failed=0`, and `runtime-ai-lv3 : ok=305 changed=4 failed=0`.
- Post-verify evidence in `receipts/live-applies/evidence/2026-04-02-ws-0319-mainline-post-verify-r9.txt` confirms the runtime-ai Traefik and Dapr substrate, Apache Tika, Gotenberg, Tesseract OCR, Nomad namespace membership, monitoring guest Docker chains, legacy runtime retirement, and authenticated `/v1/gotenberg` route all succeed together on the exact-main replay.
- Failure evidence in `receipts/live-applies/evidence/2026-04-02-ws-0319-runtime-ai-pool-live-apply-r10.txt` and `receipts/live-applies/evidence/2026-04-02-ws-0319-runtime-ai-pool-live-apply-r11.txt` records the two key rollout hazards that shaped the final fix:
  broad guest-firewall replay touched `docker-runtime-lv3`, and a monitoring-only replay still needed bounded Docker recovery after nftables evaluation.
- `receipts/live-applies/evidence/2026-04-02-ws-0319-docker-runtime-lv3-bridge-chain-manual-recovery-r1.txt` preserves the earlier shared-runtime manual recovery that was required during troubleshooting before the final monitoring-only approach existed.
