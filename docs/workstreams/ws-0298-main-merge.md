# Workstream ws-0298-main-merge

- ADR: [ADR 0298](../adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- Title: Integrate ADR 0298 exact-main replay onto `origin/main`
- Status: ready_for_merge
- Included In Repo Version: 0.177.114
- Platform Version Observed During Integration: 0.130.74
- Release Date: 2026-03-31
- Live Applied On: not yet
- Branch: `codex/ws-0298-main-merge-r1`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0298-main-merge-r1`
- Owner: codex
- Depends On: `ws-0298-live-apply`

## Purpose

Carry the verified ADR 0298 SBOM and CVE scanning surfaces onto the newest
available `origin/main`, rerun the full managed-image refresh from committed
source on that synchronized baseline, and only then update the protected
release and canonical-truth surfaces from the resulting exact-main tree.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0298-main-merge.md`
- `docs/workstreams/ws-0298-live-apply.md`
- `docs/adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/sbom-cve-scanning.md`
- `docs/runbooks/artifact-cache-runtime.md`
- `docs/runbooks/configure-build-artifact-cache.md`
- `docs/runbooks/configure-ntfy.md`
- `docs/runbooks/container-image-policy.md`
- `docs/runbooks/docker-runtime-disk-pressure.md`
- `docs/runbooks/security-posture-reporting.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `Makefile`
- `.gitea/workflows/validate.yml`
- `.github/workflows/validate.yml`
- `callback_plugins/structured_log.py`
- `.config-locations.yaml`
- `config/ansible-role-idempotency.yml`
- `config/event-taxonomy.yaml`
- `config/ntfy/server.yml`
- `config/sbom-scanner.json`
- `config/workflow-catalog.json`
- `config/windmill/scripts/sbom-refresh.py`
- `inventory/host_vars/proxmox_florin.yml`
- `receipts/ops-portal-snapshot.html`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`
- `collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/docker-compose.yml.j2`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/handlers/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_network/templates/vm.fw.j2`
- `playbooks/gitea.yml`
- `playbooks/tasks/docker-publication-assert.yml`
- `playbooks/tasks/generate-host-sbom.yml`
- `playbooks/tasks/security-scan.yml`
- `playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/generate-host-sbom.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/security-scan.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`
- `scripts/container_image_policy.py`
- `scripts/managed_image_gate.py`
- `scripts/sbom_refresh.py`
- `scripts/sbom_scanner.py`
- `scripts/upgrade_container_image.py`
- `tests/test_container_image_policy.py`
- `tests/test_artifact_cache_runtime_role.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_fault_injection_repo_surfaces.py`
- `tests/test_generate_host_sbom_task.py`
- `tests/test_ntfy_runtime_config.py`
- `tests/test_post_verify_tasks.py`
- `tests/test_sbom_refresh_windmill_wrapper.py`
- `tests/test_sbom_scanner.py`
- `tests/test_windmill_default_operations_surface.py`
- `tests/test_windmill_operator_admin_app.py`
- `tests/unit/test_event_taxonomy.py`
- `receipts/sbom/`
- `receipts/cve/`
- `receipts/live-applies/2026-03-30-adr-0298-*`
- `receipts/live-applies/evidence/2026-03-30-ws-0298-*`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`

## Integration Notes

- `origin/main` currently points to `bb94f851a3398daaceb8348280afdd4adb6815d1`
  with release `0.177.113`; the workstream branch must be replayed on that
  exact baseline instead of the older `0.177.112` snapshot used to start this
  merge worktree.
- The current exact-main carryover also aligns `config/sbom-scanner.json` and
  the SBOM/cache runbooks with the dedicated `artifact-cache-lv3`
  (`10.10.10.80`) cache plane adopted by ADR 0296.
- The merge adds the missing Docker socket mount for
  `windmill_worker_native` in the committed compose template and test surface so
  the native worker can run `scripts/sbom_refresh.py` against the local Docker
  API when the live compose file reflects the current repo state.
- The shared `/srv/proxmox_florin_server` checkout on `docker-runtime-lv3` was
  repeatedly overwritten by concurrent Windmill replays, so the exact-main
  verification switched to isolated runtime packages copied onto the build and
  runtime hosts instead of trusting the shared worker mirror.

## Verification

- `git fetch origin --prune` confirmed the merge baseline stayed on
  `bb94f851a3398daaceb8348280afdd4adb6815d1` / release `0.177.113` before the
  final integration pass.
- `uv run --with pytest pytest tests/test_windmill_operator_admin_app.py tests/test_sbom_refresh_windmill_wrapper.py tests/test_sbom_scanner.py tests/test_post_verify_tasks.py -q`
  passed on the merge tree with `28 passed in 0.64s`.
- `make managed-image-gate BASELINE_REVISION=origin/main` passed on the merge
  tree and reported `No managed image refs changed from the baseline revision.`
- The repo-wide validation path was exercised through `make validate`. The
  exact-main passes exposed a Python 3.10 compatibility gap in both
  `structured_log.py` callback copies plus stale canonical-truth and generated
  architecture surfaces; the merge tree fixes those imports and regenerates the
  affected files. The follow-up `generated-docs`,
  `generated-portals agent-standards`, and
  `workstream-surfaces agent-standards data-models` lanes all passed on the
  updated tree.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-sbom-refresh-open-webui-r10-build-host.txt`
  shows the exact-main isolated package refreshed the previously problematic
  `open_webui_runtime` image successfully on `docker-build-lv3`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-sbom-refresh-full-r3-build-host.txt`
  records a successful exact-main full catalog refresh with
  `Scanned 60 managed images` and the emitted `REPORT_JSON=...` summary.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-windmill-worker-native-docker-socket-r1.txt`
  captured a live recreation of `windmill_worker_native` with
  `DOCKER_SOCK_PRESENT` and `DOCKER_API_OK`.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-runtime-compose-state-r1.txt`
  later showed the live `/opt/windmill/docker-compose.yml` had already lost the
  native-worker Docker socket mount again, proving a concurrent replay
  overwrote the runtime compose file after the targeted fix landed.
- `receipts/live-applies/evidence/2026-03-31-ws-0298-main-merge-controller-reachability-r1.txt`
  shows the controller could still reach `docker-runtime-lv3` while
  `docker-build-lv3` and `artifact-cache-lv3` timed out, so the workstream did
  not claim a new platform-version bump from an unstable control-plane moment.

## Outcome

- Release `0.177.114` integrates ADR 0298's committed repo surfaces onto
  `main`, including the Syft/Grype scanner path, the dedicated artifact-cache
  alignment, and the `windmill_worker_native` Docker socket contract.
- ADR 0298 is now implemented in repo version `0.177.114`.
- `versions/stack.yaml`, `build/platform-manifest.json`, and the top-level
  `README.md` status summary remain unchanged because the current platform
  baseline stays at `0.130.74`.
- A stable main-based runtime replay from `docker-runtime-lv3` is still needed
  before ADR 0298 can be marked live-applied and before any platform-version
  bump is recorded.
