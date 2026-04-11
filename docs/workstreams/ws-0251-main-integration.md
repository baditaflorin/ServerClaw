# Workstream ws-0251-main-integration

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Integrate ADR 0251 exact-main durable verification onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.87
- Platform Version Observed During Integration: 0.130.59
- Release Date: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0251-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0251-live-apply-r2`
- Owner: codex
- Depends On: `ws-0251-live-apply`, `ws-0251-live-apply-r2`

## Purpose

Carry ADR 0251's verified exact-main durable verification onto the already
landed `0.177.86` mainline, refresh the protected release and canonical-truth
surfaces for repository version `0.177.87`, and publish one structured receipt
that records the current host, worker, promotion-gate, API-gateway, and
ops-portal state on the latest realistic `origin/main` baseline.

## Shared Surfaces

- `workstreams.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `build/platform-manifest.json`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.87.md`
- `versions/stack.yaml`
- `docs/adr/.index.yaml`
- `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`
- `docs/workstreams/ws-0251-live-apply.md`
- `docs/workstreams/ws-0251-live-apply-r2.md`
- `docs/workstreams/ws-0251-main-integration.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0251-exact-main-durable-verification.txt`

## Verification

- `git fetch origin --prune` advanced `origin/main` to
  `dfabe86676e6940382c18dfbc836ac3f3ea7206c`, which still carries ADR 0251 on
  repository version `0.177.86` while the verified platform baseline now reads
  `0.130.59`; this follow-up records the exact-main durable verification on top
  of that latest realistic baseline.
- SSH verification on 2026-03-29 confirmed the Proxmox host is still
  `proxmox-host` with
  `pve-manager/9.1.6/71482d1833ded40a` and kernel `6.17.13-2-pve`.
- The authenticated runtime-assurance API returned `status 200` at
  `https://api.example.com/v1/platform/runtime-assurance` with
  `generated_at: 2026-03-29T20:35:32Z`, `total: 47`, `pass: 28`,
  `degraded: 19`, `failed: 0`, and `unknown: 0`.
- Guest-local verification on `docker-runtime` confirmed
  `/srv/proxmox-host_server/scripts/stage_smoke.py` is present, both
  `scripts/promotion_pipeline.py` and
  `scripts/ops_portal/runtime_assurance.py` import it, and
  `python3 /srv/proxmox-host_server/config/windmill/scripts/gate-status.py --repo-path /srv/proxmox-host_server`
  returned `status: "ok"` with a passed `post_merge_run` executed at
  `2026-03-29T19:37:24.365664+00:00`.
- Guest-local ops-portal verification on `docker-runtime` returned
  `status 200` for both `http://127.0.0.1:8092/partials/overview` and
  `http://127.0.0.1:8092/partials/runtime-assurance`, and neither partial
  rendered the degraded runtime-assurance banner.
- The governed promotion-gate negative-path replay on `docker-runtime`
  still rejected the stale staged Grafana receipt with return code `1`; the
  current reasons were Prometheus SLO query timeouts, projected vCPU
  commitment `36.0` exceeding target `22.5`, and the receipt age exceeding
  twenty-four hours, while the returned `stage_smoke_gate` payload stayed
  `enforced=false` with `required_suite_ids=[]` and `observed_suites=[]`.

## Outcome

- Release `0.177.87` carries ADR 0251's exact-main durable verification onto
  `main`.
- Platform version remains on the already-verified `0.130.59` mainline
  baseline; this follow-up records ADR 0251 as fully live without advancing the
  platform to a newer state.
- `receipts/live-applies/2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply.json`
  becomes the canonical exact-main receipt, while the earlier
  `2026-03-29-adr-0251-stage-smoke-suites-live-apply.json` receipt remains the
  preserved first isolated-worktree live apply.
