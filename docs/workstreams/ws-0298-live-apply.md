# Workstream ws-0298-live-apply: Live Apply ADR 0298 From Latest `origin/main`

- ADR: [ADR 0298](../adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- Title: Live apply platform-wide SBOM generation and continuous CVE scanning with Syft and Grype
- Status: blocked
- Included In Repo Version: 0.177.114
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0298-sbom-cve-scanning-branch-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-sbom-refresh-full-r3-build-host.txt`
- Live Applied In Platform Version: not yet
- Implemented On: 2026-03-31
- Live Applied On: branch-local partial verification on 2026-03-30; exact-main build-host verification on 2026-03-31
- Branch: `codex/ws-0298-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-live-apply-r2`
- Owner: codex
- Depends On: `adr-0068`, `adr-0087`, `adr-0102`, `adr-0165`, `adr-0295`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0298`, `docs/workstreams/ws-0298-live-apply.md`, `docs/runbooks/sbom-cve-scanning.md`, `docs/runbooks/container-image-policy.md`, `docs/runbooks/security-posture-reporting.md`, `Makefile`, `.gitea/workflows/validate.yml`, `.github/workflows/validate.yml`, `.config-locations.yaml`, `config/sbom-scanner.json`, `config/workflow-catalog.json`, `config/windmill/scripts/sbom-refresh.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `playbooks/gitea.yml`, `playbooks/tasks/generate-host-sbom.yml`, `playbooks/tasks/security-scan.yml`, `playbooks/tasks/post-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/generate-host-sbom.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/security-scan.yml`, `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`, `scripts/container_image_policy.py`, `scripts/managed_image_gate.py`, `scripts/sbom_refresh.py`, `scripts/sbom_scanner.py`, `scripts/upgrade_container_image.py`, `tests/test_container_image_policy.py`, `tests/test_post_verify_tasks.py`, `tests/test_sbom_refresh_windmill_wrapper.py`, `tests/test_sbom_scanner.py`, `tests/test_windmill_default_operations_surface.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/sbom/`, `receipts/cve/`, `receipts/live-applies/`

## Purpose

Implement ADR 0298 by pinning the Syft and Grype tooling, wiring the
managed-image validation gate, adding the daily Windmill refresh workflow, and
making host SBOM generation part of the live converge and security-scan paths.

## Branch-Local Delivery

- This workstream was rebased onto the latest `origin/main` before the ADR 0298
  repo surfaces were edited.
- Protected integration files remain untouched on this branch:
  `VERSION`, release sections in `changelog.md`, the top-level `README.md`
  status summary, and `versions/stack.yaml`.
- Branch-local live-apply evidence will be stored under
  `receipts/live-applies/2026-03-30-adr-0298-*` and
  `receipts/live-applies/evidence/2026-03-30-ws-0298-*`.

## Completed Verification

- `python3 -m py_compile` for the new scanner, gate, and Windmill wrapper paths
- targeted `pytest` for scanner, wrapper, Windmill defaults, and post-verify
  wiring
- `make managed-image-gate BASELINE_REVISION=origin/main`
- `./scripts/validate_repo.sh agent-standards`
- live replay of the affected converge paths plus targeted worker-side
  `sbom_refresh.py` runs
- exact-main isolated refresh verification from `docker-build-lv3`, including a
  successful `open_webui_runtime` replay and a full catalog refresh of
  60 managed images from committed source on the synchronized mainline tree

## Live Evidence

- `receipts/live-applies/evidence/2026-03-30-ws-0298-converge-windmill-r12.txt`
  converged the Windmill worker checkout on `docker-runtime-lv3`, refreshed the
  seeded workflows, and fetched a fresh host SBOM receipt for
  `host-docker-runtime-lv3-2026-03-30.cdx.json`.
- `receipts/live-applies/evidence/2026-03-30-ws-0298-runtime-scanner-sha-r2.txt`
  confirms the live worker checkout now carries the patched
  `scripts/sbom_scanner.py` with native Linux `syft` fallback.
- `receipts/live-applies/evidence/2026-03-30-ws-0298-sbom-refresh-open-webui-r4.txt`
  shows the previously failing `open_webui_runtime` image now refreshes
  successfully end to end from `docker-runtime-lv3`.
- `receipts/live-applies/evidence/2026-03-30-ws-0298-sbom-refresh-full-r1.txt`
  and `receipts/live-applies/evidence/2026-03-30-ws-0298-sbom-refresh-full-r2.txt`
  show the remaining blocker during full-platform refresh attempts.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-sbom-refresh-open-webui-r10-build-host.txt`
  shows the exact-main isolated package refreshed `open_webui_runtime`
  successfully from `docker-build-lv3`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-sbom-refresh-full-r3-build-host.txt`
  records the full exact-main catalog refresh succeeding with
  `Scanned 60 managed images`.

## Blocker

The worker-side scanner failure that previously ended with Docker
`error waiting for container: unexpected EOF` is fixed by preferring a native
Linux `syft` binary when available. A sustained full-platform refresh is still
blocked by unstable runtime-to-artifact-cache connectivity:

- `receipts/live-applies/evidence/2026-03-30-ws-0298-artifact-cache-build-listeners-r9.txt`
  and `...-r10.txt` show `docker-build-lv3` continued listening on ports
  `5001` through `5004`.
- `receipts/live-applies/evidence/2026-03-30-ws-0298-artifact-cache-runtime-socket-r7.txt`
  and `...-r9.txt` show `docker-runtime-lv3` losing reachability to all four
  mirror ports under full refresh load.
- `receipts/live-applies/evidence/2026-03-30-ws-0298-guest-network-policy-r9.txt`
  restored runtime mirror reachability for the relevant hosts, but the governed
  replay later failed on an unrelated `postgres-replica-lv3` SSH problem after
  the runtime/build/proxmox sections had already succeeded.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-windmill-worker-native-docker-socket-r1.txt`
  proves the native worker can execute with a live Docker socket when the
  compose file reflects the current repo template.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-runtime-compose-state-r1.txt`
  later shows the live `/opt/windmill/docker-compose.yml` on
  `docker-runtime-lv3` no longer included that Docker socket mount, which means
  a concurrent replay overwrote the runtime compose file after the targeted
  fix.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-controller-reachability-r1.txt`
  shows the controller could still reach `docker-runtime-lv3` while
  `docker-build-lv3` and `artifact-cache-lv3` timed out entirely, so the
  remaining failure mode was broader guest-network/control-plane instability
  rather than an ADR 0298 scanner regression.

Until the ADR 0295 cache plane stays stable for a full catalog refresh from
`docker-runtime-lv3`, this workstream should not be marked live-applied.

## Validation Notes

- The exact-main merge tree exercised `make validate` and showed that the
  remaining repository-level follow-up was a Python 3.10 compatibility fix for
  the structured-log callback plus regeneration of stale canonical-truth and
  architecture surfaces, not an ADR 0298 scanner regression.

## Merge Notes

- Release `0.177.114` now carries ADR 0298 onto `main` as an implemented repo
  surface without bumping `platform_version`.
- The remaining live-apply step is a stable main-based replay from
  `docker-runtime-lv3` once the shared Windmill compose/checkout drift and the
  controller-to-build/cache guest reachability are stable again.
