# Workstream ws-0274-minio-live-apply: Live Apply ADR 0274 MinIO From Latest `origin/main`

- ADR: [ADR 0274](../adr/0274-minio-as-the-s3-compatible-object-storage-layer.md)
- Title: Deploy the shared MinIO object storage layer on `docker-runtime`, rewire the first S3 consumers, and record the first platform version where ADR 0274 is true
- Status: live_applied
- Included In Repo Version: 0.177.124
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0274-minio-object-storage-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.79
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Release Date: 2026-03-31
- Branch: `codex/ws-0274-mainline-refresh-v6`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0274-mainline-refresh-v6`
- Owner: codex
- Depends On: `adr-0021`, `adr-0077`, `adr-0143`, `adr-0146`, `adr-0198`, `adr-0274`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0274`, `docs/workstreams/ws-0274-minio-live-apply.md`, `docs/runbooks/minio-object-storage.md`, `workstreams.yaml`, repo onboarding metadata, `inventory/host_vars/proxmox-host.yml`, generated platform vars/catalogs/SLO artifacts, MinIO runtime and consumer roles, and `receipts/live-applies/`

## Scope

- add a repo-managed standalone MinIO runtime on `docker-runtime`
- publish the MinIO API and console through the shared edge with governed DNS/topology metadata
- migrate the launch consumers from ADR 0274 onto MinIO buckets: Loki, Langfuse, Gitea LFS, and RAG staging
- live apply the exact branch implementation, verify it end to end, and capture a receipt with repo + platform evidence

## Non-Goals

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

- `docker-runtime` runs the shared MinIO API and console listeners
- `minio.example.com` serves the S3-compatible API over TLS at the edge
- `minio-console.example.com` serves the authenticated MinIO console over TLS at the edge
- `loki-chunks`, `langfuse-exports`, `gitea-lfs`, and `rag-staging` exist with their expected policies on MinIO
- Loki, Langfuse, Gitea, and the RAG platform context runtime all use the shared MinIO endpoint successfully

## Ownership Notes

- this workstream owns the exact-main MinIO live apply and the shared object-storage runtime surfaces; shared topology, edge, and catalog files remain under their existing repo contracts
- the branch intentionally used a dedicated clean worktree because another local worktree already held unrelated uncommitted edits under the same `ws-0274-live-apply` name
- latest `origin/main` already used `ws-0274-live-apply` for the other duplicated ADR 0274, so this branch disambiguated the MinIO rollout as `ws-0274-minio-live-apply`
- the final integration step on `main` updates the protected release surfaces, the canonical platform version, and the merged README status summary together with the canonical receipt

## Verification

- the latest realistic integration baseline was refreshed from `origin/main` commit `14b18869a2ff421ec12596bd199af0adb09a95b8`, which still carried repository version `0.177.123` and platform version `0.130.78`
- focused pytest for the MinIO, Restic, and OpenBao recovery surfaces passed on the release candidate together with `make syntax-check-minio`, `make syntax-check-restic-config-backup`, and `ansible-playbook -i inventory/hosts.yml playbooks/openbao.yml --syntax-check`
- the exact-main MinIO replay succeeded on the pre-release baseline and preserved public API health, authenticated console redirect, and the event-driven Restic backup trigger as committed evidence
- the first release-candidate replay preserved an unrelated Docker recovery hiccup where the shared Keycloak compose group retried while local OpenBao was sealed; the failure was documented, the shared stack recovered cleanly, and the canonical receipt keeps that evidence instead of hiding it
- controller-side `make restic-config-backup env=production` and `make restic-config-restore-verify env=production` re-confirm the shared MinIO-backed backup and restore path for the new `minio-root` repository contract
- final repo validation passes include canonical-truth regeneration, live-apply receipt validation, generated docs, data models, workstream ownership, and the remote validation gates from the integrated release tree

## Notes

- `receipts/live-applies/2026-03-30-adr-0274-minio-object-storage-live-apply.json` remains the historical branch-local proof from the pre-mainline rollout; the canonical truth now lives in the 2026-03-31 mainline receipt.
- Outline and Plane intentionally keep their local MinIO sidecars; this workstream only establishes the shared object-storage layer and the first governed consumers.
