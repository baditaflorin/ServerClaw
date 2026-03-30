# Workstream ws-0260-main-integration

- ADR: [ADR 0260](../adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md)
- Title: Integrate ADR 0260 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: 0.177.93
- Platform Version Observed During Integration: 0.130.62
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0260-final-main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0260-final-main`
- Owner: codex
- Depends On: `ws-0260-live-apply`

## Purpose

Carry the verified ADR 0260 Nextcloud personal data plane onto the newest
available `origin/main`, recut the protected release and canonical-truth
surfaces from that synchronized baseline, rerun the exact-main Nextcloud live
apply on the merged tree, and record the canonical receipt that makes the
branch-local proof authoritative on `main`.

## Shared Surfaces

- `workstreams.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/0.177.93.md`
- `docs/release-notes/README.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md`
- `docs/workstreams/ws-0260-live-apply.md`
- `docs/workstreams/ws-0260-main-integration.md`
- `docs/runbooks/configure-nextcloud.md`
- `playbooks/nextcloud.yml`
- `playbooks/services/nextcloud.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nextcloud_postgres/**`
- `collections/ansible_collections/lv3/platform/roles/nextcloud_runtime/**`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `tests/test_nextcloud_playbook.py`
- `tests/test_nextcloud_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
- `receipts/live-applies/2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0260-mainline-*.txt`

## Verification

- `git fetch origin --prune` confirmed the newest available baseline before the
  final recut remained `origin/main` commit
  `bbb0f66b8ec995dfa3ecdd7bac9156ed664157cc`, which already carried repository
  version `0.177.92` and platform version `0.130.61`.
- The final exact-main proof was replayed from committed source
  `2b0787aeac03f143ef50cf3e4f2c17f1a81aa3b0`, which preserved repository
  version `0.177.93` while hardening mutable Nextcloud OCC convergence against
  concurrent Docker interruptions on the shared host.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=nextcloud env=production`
  succeeded from that synchronized tree with final recap
  `docker-runtime-lv3 ok=181 changed=4 failed=0 skipped=109`,
  `nginx-lv3 ok=39 changed=4 failed=0 skipped=7`,
  `postgres-lv3 ok=52 changed=0 failed=0 skipped=14`, and
  `localhost ok=18 changed=0 failed=0 skipped=3`.
- Public verification returned
  `{"installed":true,"maintenance":false,"needsDbUpgrade":false,"versionstring":"33.0.1"...}`
  from `https://cloud.lv3.org/status.php`, and both
  `https://cloud.lv3.org/.well-known/caldav` plus
  `https://cloud.lv3.org/.well-known/carddav` returned `HTTP/2 301` with
  `location: https://cloud.lv3.org/remote.php/dav/`.
- Guest-local verification through the managed Proxmox jump path returned the
  same `status.php` payload from `http://10.10.10.20:8084/status.php`, showed
  `nextcloud-app` listening on `0.0.0.0:8084->80/tcp`, kept
  `backgroundjobs_mode=cron`, and confirmed the bootstrap `ops` account
  remained enabled in the `admin` group.
- The follow-up container health inspection confirmed both `nextcloud-redis`
  and `nextcloud-openbao-agent` reached `Status: healthy`, proving the replay
  preserved the post-apply runtime health and the shared OpenBao recovery path.
- Repo validation also passed on the final branch tree:
  `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs`,
  `uv run --with pyyaml python3 scripts/canonical_truth.py --check`,
  `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`,
  `git diff --check`, and `make pre-push-gate`.

## Outcome

- Release `0.177.93` carries ADR 0260's exact-main replay onto `main`.
- Platform version `0.130.62` becomes the current integrated platform baseline
  because the synchronized release `0.177.93` was live-applied successfully
  from the refreshed mainline tree.
- `receipts/live-applies/2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`
  is the canonical exact-main proof for the Nextcloud personal data plane from
  committed source `2b0787aeac03f143ef50cf3e4f2c17f1a81aa3b0`, superseding the
  earlier 2026-03-29 mainline receipt.
