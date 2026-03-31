# Workstream ws-0284-live-apply: Live Apply ADR 0284 From Latest `origin/main`

- ADR: [ADR 0284](../adr/0284-piper-tts-as-the-cpu-neural-text-to-speech-service.md)
- Title: Deploy the private Piper text-to-speech runtime and verify the live `/api/tts` path
- Status: ready_for_merge
- Included In Repo Version: pending merge to main
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0284-piper-live-apply.json`
- Canonical Mainline Receipt: pending exact-main integration
- Live Applied In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0284-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0284-live-apply`
- Owner: codex
- Depends On: `adr-0107`, `adr-0165`, `adr-0293`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0284`, `docs/workstreams/ws-0284-live-apply.md`, `docs/runbooks/configure-piper.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/command-catalog.json`, `config/workflow-catalog.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/slo_rules.yml`, `config/grafana/dashboards/slo-overview.json`, `playbooks/piper.yml`, `playbooks/services/piper.yml`, `collections/ansible_collections/lv3/platform/roles/piper_runtime/`, `tests/test_generate_platform_vars.py`, `tests/test_piper_playbook.py`, `tests/test_piper_runtime_role.py`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/ops-portal-snapshot.html`, `docs/adr/.index.yaml`, `receipts/live-applies/`, `workstreams.yaml`

## Purpose

Implement ADR 0284 from the current `origin/main` baseline by delivering the
private Piper runtime on `docker-runtime-lv3`, correcting the live port
assignment after collision with Temporal UI, preserving the recovery hardening
discovered during the replay, and recording enough branch-local evidence for a
safe exact-main merge.

## Branch-Local Delivery

- `f268ea8fe` brought the Piper runtime, service playbooks, verification role,
  default voice contract, generated catalog updates, and the initial runbook
  surfaces onto the latest synchronized `origin/main` baseline.
- The branch-local live replay exposed two real latest-main issues that were
  not visible in the original implementation commit: the Docker image build
  path could fail on stale bridge and build-network state, and Piper's
  canonical private port `8099` collided with the already-live Temporal UI
  listener on `127.0.0.1:8099`.
- The current branch carries the recovery hardening that fixed the first
  failure by switching the Piper image build onto the repo's safer
  temp-build-dir plus legacy-builder path with `DOCKER_BUILDKIT=0`,
  `--network host`, stale build-network recovery, and compose startup retry
  logic that also repairs stale Docker NAT or compose-network state before
  retrying.
- The current branch also corrects Piper's canonical private port from `8099`
  to `8100` across inventory, generated service catalogs, SLO targets,
  workflow verification commands, runbooks, and tests so the latest-main tree
  no longer collides with Temporal UI while preserving Piper's private-only
  contract.

## Verification

- The refreshed branch reran `make generate-platform-vars`,
  `uv run --with pyyaml python scripts/generate_slo_rules.py --write`, and
  `make generate-ops-portal` after the port correction so the generated
  topology and portal surfaces match the new Piper listener.
- The focused Piper regression slice passed with
  `uv run --with pytest --with pyyaml python -m pytest -q tests/test_piper_runtime_role.py tests/test_piper_playbook.py tests/test_generate_platform_vars.py`,
  returning `45 passed in 16.21s`.
- `make syntax-check-piper`, `./scripts/validate_repo.sh health-probes`, and
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  all passed on the corrected branch.
- The first governed replay failed because Docker tried to create a build
  endpoint on a missing bridge network; the full transcript is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-converge-piper-r1.txt`.
- The second governed replay reached service startup and then failed on the
  real port conflict; `receipts/live-applies/evidence/2026-03-31-ws-0284-converge-piper-r2.txt`
  plus the direct `ss` and `docker ps` checks captured that `temporal-ui`
  already owned `127.0.0.1:8099`.
- After correcting Piper to `8100`, the third governed replay succeeded with
  final recap `docker-runtime-lv3 : ok=124 changed=8 unreachable=0 failed=0 skipped=25 rescued=1 ignored=0`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-converge-piper-r3.txt`.
- Direct guest-local verification is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-piper-local-http-r1.txt`
  and confirmed both published bindings for container port `5000`, a healthy
  `/healthz` payload, and the default voice `en_US-ryan-medium`.
- Host-path synthesis verification is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-piper-host-path-tts-r1.txt`
  and returned a valid WAV payload summary
  `{"content_type":"audio/wav","riff":"RIFF","wave":"WAVE","bytes":104492}`.
- The governed wrapper transcript in
  `receipts/live-applies/evidence/2026-03-31-ws-0284-live-apply-wrapper-r1.txt`
  shows the expected branch-local stop on stale canonical truth because
  `README.md` is intentionally protected until the exact-main integration step.

## Merge-To-Main Remaining

- Refresh the protected canonical-truth surfaces from `main`, including
  `README.md`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/`, `build/platform-manifest.json`, and
  `versions/stack.yaml`.
- Rerun the governed `live-apply-service` wrapper from the exact-main tree so
  the canonical mainline receipt captures the committed source instead of only
  the branch-local replay evidence.
- Update this workstream from `ready_for_merge` to `merged`, replace the
  pending repo-version and canonical-receipt placeholders with exact-main
  values, and then push `origin/main`.

## Outcome

- ADR 0284 is now live on the current verified platform baseline `0.130.74`
  from the dedicated workstream branch.
- The branch-local evidence proves both the recovery hardening and the `8100`
  port correction were necessary latest-main fixes, not speculative cleanup.
- No unresolved Piper runtime defect remains on the workstream branch; the
  remaining work is the protected exact-main integration and receipt refresh.
