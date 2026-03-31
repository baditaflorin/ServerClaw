# Workstream ws-0274-minio-live-apply: Live Apply ADR 0274 MinIO From Latest `origin/main`

- ADR: [ADR 0274](../adr/0274-minio-as-the-s3-compatible-object-storage-layer.md)
- Title: Deploy the shared MinIO object storage layer on `docker-runtime-lv3`, rewire the first S3 consumers, and record the first platform version where ADR 0274 is true
- Status: in_progress
- Implemented In Repo Version: pending next main release
- Latest Verified Receipt: `receipts/live-applies/2026-03-30-adr-0274-minio-object-storage-live-apply.json`
- Live Applied In Platform Version: 0.130.69
- Latest Observed On Platform Version: 0.130.69
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0274-mainline-refresh-v6`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0274-mainline-refresh-v6`
- Owner: codex
- Depends On: `adr-0021`, `adr-0077`, `adr-0143`, `adr-0146`, `adr-0198`, `adr-0274`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0274`, `docs/workstreams/ws-0274-minio-live-apply.md`, `docs/runbooks/minio-object-storage.md`, `workstreams.yaml`, repo onboarding metadata, `inventory/host_vars/proxmox_florin.yml`, generated platform vars/catalogs/SLO artifacts, MinIO runtime and consumer roles, and `receipts/live-applies/`

## Scope

- add a repo-managed standalone MinIO runtime on `docker-runtime-lv3`
- publish the MinIO API and console through the shared edge with governed DNS/topology metadata
- migrate the launch consumers from ADR 0274 onto MinIO buckets: Loki, Langfuse, Gitea LFS, and RAG staging
- live apply the exact branch implementation, verify it end to end, and capture a receipt with repo + platform evidence

## Non-Goals

- bumping `VERSION`, `changelog.md`, the top-level integrated `README.md`, or `versions/stack.yaml` on this workstream branch
- migrating non-launch consumers such as Outline or Plane off their local MinIO sidecars
- turning standalone MinIO into an HA storage cluster

## Expected Repo Surfaces

- `workstreams.yaml`
- `.config-locations.yaml`
- `.repo-structure.yaml`
- `docs/workstreams/ws-0274-minio-live-apply.md`
- `docs/adr/0274-minio-as-the-s3-compatible-object-storage-layer.md`
- `docs/runbooks/minio-object-storage.md`
- `playbooks/minio.yml`
- `playbooks/services/minio.yml`
- `collections/ansible_collections/lv3/platform/playbooks/minio.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/minio.yml`
- `collections/ansible_collections/lv3/platform/roles/minio_runtime/`
- `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`
- `collections/ansible_collections/lv3/platform/roles/langfuse_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`
- `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/plane_runtime/defaults/main.yml`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/slo-catalog.json`
- `config/grafana/dashboards/minio.json`
- `config/grafana/dashboards/slo-overview.json`
- `config/alertmanager/rules/minio.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `receipts/image-scans/2026-03-30-minio-runtime.json`
- `receipts/image-scans/2026-03-30-minio-runtime.trivy.json`
- topology/catalog/runbook/test surfaces needed to describe and validate the MinIO rollout

## Expected Live Surfaces

- `docker-runtime-lv3` runs the shared MinIO API and console listeners
- `minio.lv3.org` serves the S3-compatible API over TLS at the edge
- `minio-console.lv3.org` serves the authenticated MinIO console over TLS at the edge
- `loki-chunks`, `langfuse-exports`, `gitea-lfs`, and `rag-staging` exist with their expected policies on MinIO
- Loki, Langfuse, Gitea, and the RAG platform context runtime all use the shared MinIO endpoint successfully

## Ownership Notes

- this workstream owns the exact-main live apply and the new MinIO runtime surfaces; shared topology, edge, and catalog files remain under their existing repo contracts
- the branch intentionally uses a dedicated clean worktree because another local worktree already held unrelated uncommitted edits under the same `ws-0274-live-apply` name
- latest `origin/main` already uses `ws-0274-live-apply` for the other duplicated ADR 0274, so this branch disambiguates the MinIO rollout as `ws-0274-minio-live-apply`
- shared integration truth files stay untouched here unless this branch becomes the final synchronized `main` integration step

## Verification

- `git fetch origin && git merge-base --is-ancestor origin/main HEAD`
- focused unit tests for the MinIO runtime and all rewired consumers
- syntax checks and converge runs for the MinIO service plus each affected consumer path
- live MinIO bucket, policy, and endpoint probes from both the controller and the target guests
- repo-wide validation gates including generated artifacts, data models, workstream ownership, and docs/portal generation

## Merge-To-Main Remaining

- cut the next synchronized main release and record the first merged repo version where ADR 0274 is true
- replay the verified MinIO rollout from merged `main` so `versions/stack.yaml` can advance from `0.130.69` to the first exact-main platform version that includes this ADR
- refresh the protected integration surfaces on `main` only: `VERSION`, `changelog.md`, the top-level `README.md` status summary, and `versions/stack.yaml`
