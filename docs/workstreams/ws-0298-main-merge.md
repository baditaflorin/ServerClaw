# Workstream ws-0298-main-merge

- ADR: [ADR 0298](../adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- Title: Integrate ADR 0298 exact-main replay onto `origin/main`
- Status: in_progress
- Included In Repo Version: pending
- Platform Version Observed During Integration: 0.130.73
- Release Date: pending
- Live Applied On: pending
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
- `docs/site-generated/architecture/dependency-graph.md`
- `Makefile`
- `.gitea/workflows/validate.yml`
- `.github/workflows/validate.yml`
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
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
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

- `origin/main` currently points to `58dad5d37ae16ceb3a73bc2fe4554b2a449e8f83`
  with release `0.177.112`; the workstream branch must be replayed on that
  exact baseline instead of the older `0.177.111` snapshot used to start this
  merge worktree.
- The earlier branch-local live apply fixed the native scanner path and proved
  `open_webui_runtime` on the worker checkout, but the full catalog refresh was
  still blocked by runtime-to-artifact-cache instability under load.
- The current exact-main carryover also aligns `config/sbom-scanner.json` and
  the SBOM/cache runbooks with the dedicated `artifact-cache-lv3`
  (`10.10.10.80`) cache plane adopted by ADR 0296.
- This exact-main integration must not mark ADR 0298 live-applied until a full
  `scripts/sbom_refresh.py --skip-db-update --print-report-json` run completes
  from `docker-runtime-lv3` on the synchronized mainline tree.
