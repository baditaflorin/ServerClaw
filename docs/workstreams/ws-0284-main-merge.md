# Workstream ws-0284-main-merge

- ADR: [ADR 0284](../adr/0284-piper-tts-as-the-cpu-neural-text-to-speech-service.md)
- Title: Integrate ADR 0284 Piper exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.113
- Platform Version Observed During Integration: 0.130.74
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0284-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0284-live-apply`
- Owner: codex
- Depends On: `ws-0284-live-apply`

## Purpose

Carry the verified ADR 0284 Piper live-apply branch onto the newest available
`origin/main`, rerun the exact-main Piper replay from committed source on that
synchronized baseline, cut the protected release and canonical-truth surfaces
from the resulting tree, and publish the private `8100` voice path on `main`
without inventing a new platform-version bump after Piper was already live on
`0.130.74`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0284-main-merge.md`
- `docs/workstreams/ws-0284-live-apply.md`
- `docs/adr/0284-piper-tts-as-the-cpu-neural-text-to-speech-service.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-piper.md`
- `inventory/host_vars/proxmox-host.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `playbooks/piper.yml`
- `playbooks/services/piper.yml`
- `collections/ansible_collections/lv3/platform/roles/piper_runtime/`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py`
- `tests/test_structured_log_callback.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_piper_playbook.py`
- `tests/test_piper_runtime_role.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-31-adr-0284-piper-live-apply.json`
- `receipts/live-applies/2026-03-31-adr-0284-piper-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-*`

## Verification

- `git fetch origin --prune` confirmed the newest realistic `origin/main`
  commit was still `58dad5d37ae16ceb3a73bc2fe4554b2a449e8f83`, carrying repo
  version `0.177.112` and platform version `0.130.74` before the final ADR
  0284 integration pass.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py`
  status, dry-run, and write executions prepared release `0.177.113` while
  preserving `platform_version: 0.130.74`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-release-status-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-release-dry-run-r1.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-release-write-r1.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=piper env=production`
  succeeded from committed source `52159758420127966e32ba7ff5c89a4cccaa31a8`
  with final recap
  `docker-runtime : ok=116 changed=3 unreachable=0 failed=0 skipped=9 rescued=0 ignored=0`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-live-apply-r1.txt`.
- Fresh exact-main guest-local verification confirmed both published bindings
  for `5000/tcp`, the healthy `/healthz` payload, and the declared default
  voice `en_US-ryan-medium`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-local-http-r1.txt`.
- Fresh exact-main host-path synthesis verification returned the valid WAV
  summary `{"content_type":"audio/wav","riff":"RIFF","wave":"WAVE","bytes":109612}`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-host-path-tts-r1.txt`.
- The first final validation pass surfaced two mainline-integration repairs:
  the local idempotency gate loaded the `structured_log` callback through a
  Python 3.10 interpreter that cannot import `datetime.UTC`, and the remote
  validation runner flagged stale generated diagram surfaces. This branch now
  carries the Python 3.10 compatibility fallback in
  `collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py`
  plus the widened callback unit coverage in
  `tests/test_structured_log_callback.py`; the failing transcripts are
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-validate-r1.txt`
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-remote-validate-r1.txt`.
- The repaired exact-main compatibility slice then passed with
  `46 passed in 4.10s` across the callback coverage, Piper role, Piper
  playbook, and platform-vars tests, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-targeted-checks-r1.txt`.
- Final repo automation and validation gates passed from the corrected exact-main
  tree, including `make check-build-server`, `make validate`,
  `make remote-validate`, `make pre-push-gate`,
  `python3 scripts/live_apply_receipts.py --validate`, and `git diff --check`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-check-build-server-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-validate-r2.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-remote-validate-r2.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-pre-push-gate-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-live-apply-receipts-validate-r2.txt`,
  and `receipts/live-applies/evidence/2026-03-31-ws-0284-mainline-git-diff-check-r2.txt`.
- The final mainline closeout then flipped `ws-0284-live-apply` to `merged`
  and `ws-0284-main-merge` to `live_applied`, regenerated the canonical truth
  and ops-portal surfaces from that terminal metadata, and passed
  `LV3_SNAPSHOT_BRANCH=main ./scripts/validate_repo.sh workstream-surfaces generated-docs generated-portals`,
  `python3 scripts/live_apply_receipts.py --validate`, and `git diff --check`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-main-candidate-validation-r1.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0284-main-candidate-live-apply-receipts-validate-r1.txt`,
  and `receipts/live-applies/evidence/2026-03-31-ws-0284-main-candidate-git-diff-check-r1.txt`.

## Outcome

- Release `0.177.113` is the integrated repo version for ADR 0284.
- Platform version remains `0.130.74` because Piper first became true on that
  baseline; the exact-main replay verifies the already-live capability on the
  newer synchronized repo truth instead of advancing `platform_version` again.
- `receipts/live-applies/2026-03-31-adr-0284-piper-mainline-live-apply.json`
  is the canonical exact-main proof for Piper on `main`, and this workstream
  now records the merged mainline closeout after the successful validation
  bundle and push-to-main preparation.
