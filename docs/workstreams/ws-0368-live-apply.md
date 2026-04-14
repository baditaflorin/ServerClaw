# Workstream ws-0368-live-apply: ADR 0368 Live Apply and Completion

- ADR: [ADR 0368](../adr/0368-docker-compose-jinja2-macro-library.md)
- Title: complete ADR 0368 live apply from the latest realistic `origin/main`
- Status: live_applied
- Included In Repo Version: `0.178.138`
- Included In Platform Version: `0.178.138`
- Branch-Local Receipt: `receipts/live-applies/2026-04-14-adr-0368-docker-compose-jinja2-macro-library-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-14-adr-0368-docker-compose-jinja2-macro-library-mainline-live-apply.json`
- Implemented On: 2026-04-14
- Latest Verified Base: `origin/main@6aeb26434724680c6da2162cd3544031b5a93f03` (`repo 0.178.137`, `platform 0.178.133`)
- Branch: `codex/ws-0368-main-publish-r4`
- Worktree: `.worktrees/ws-0368-main-publish-r4`
- Owner: codex
- Depends On: `ADR 0368`
- Conflicts With: none

## Scope

- finish the compose-macro rollout and exact-main replay repairs needed for
  truthful ADR 0368 live apply
- materialize the ignored generated worktree artifacts required for fresh-worktree
  service replays
- replay MinIO, Gitea, and Redpanda from the merged main candidate
- promote the verified result into repo and platform version `0.178.138` and
  archive the workstream cleanly

## Outcome

- The remaining Redpanda readiness bug on latest realistic main was repaired in
  `catalog/services/redpanda/service.yaml` so the verification probe reads back
  from the produced Kafka offset instead of hard-coding `offset=0`.
- `scripts/sbom_scanner.py`, `scripts/managed_image_gate.py`, and
  `scripts/upgrade_container_image.py` now resolve receipts correctly from a
  fresh worktree, which unblocked exact-main image and SBOM validation from a
  separate integration checkout.
- The fresh mainline replay initially failed because generated controller-local
  artifacts like `inventory/group_vars/platform.yml` were absent in the new
  worktree. `scripts/materialize_live_apply_worktree_artifacts.py` plus
  `scripts/generate_slo_rules.py --write` restored the expected generated state
  without reintroducing repo drift.
- Protected integration files were updated only in this final closeout step:
  `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, the release-note
  indexes, and the archived ws-0368 registry entry now all align to repo and
  platform version `0.178.138`.

## Verification

- Focused regression coverage passed on the integrated main candidate:
  `uv run --with pytest --with jsonschema pytest -q tests/test_gitea_runtime_role.py tests/test_minio_runtime_role.py tests/test_redpanda_runtime_role.py tests/test_service_definition_catalog.py tests/test_sbom_scanner.py tests/test_upgrade_container_image.py`
  returned `46 passed in 1.08s`; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-pytest-r1-0.178.138.txt`.
- Direct repo validation passed with `LV3_SNAPSHOT_BRANCH=HEAD ./scripts/validate_repo.sh agent-standards service-definitions health-probes data-models workstream-surfaces generated-docs generated-portals alert-rules`;
  evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-repo-gates-r1-0.178.138.txt`.
- Live-apply receipt schema validation passed via
  `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`;
  evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-live-apply-receipts-r1-0.178.138.txt`.
- `git diff --check` passed; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-git-diff-check-r1-0.178.138.txt`.
- `./scripts/remote_exec.sh check-build-server` passed; evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-check-build-server-r1-0.178.138.txt`.
- `make remote-validate` exercised the intended failure-and-recovery path: the
  build server could not resolve `registry.example.com` for runner images, then
  `remote_exec.sh` reran the unresolved checks locally and all blocking lanes
  passed (`workstream-surfaces`, `agent-standards`, `ansible-syntax`,
  `schema-validation`, `atlas-lint`, `policy-validation`, `iac-policy-scan`,
  `alert-rule-validation`, `type-check`, and `dependency-graph`); evidence:
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-final-remote-validate-r1-0.178.138.txt`.

## Live Apply

- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=minio env=production`
  completed on the exact-main candidate, with public health and console
  publication verification recorded in
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-minio-live-apply-r3-0.178.138.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=gitea env=production`
  completed on the exact-main candidate, with private API and signed
  release-bundle verification recorded in
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-gitea-live-apply-r1-0.178.138.txt`
  and
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-gitea-verify-r1-0.178.138.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=redpanda env=production`
  completed on the exact-main candidate, with admin, HTTP proxy, and
  schema-registry verification recorded in
  `receipts/live-applies/evidence/2026-04-14-ws-0368-mainline-redpanda-live-apply-r1-0.178.138.txt`.
- ADR 0368 now truthfully records `Implementation Status: Live applied`,
  `Implemented In Repo Version: 0.178.116`, `Implemented In Platform Version:
  0.178.138`, and `Implemented On: 2026-04-14`.

## Integration Notes

- The latest realistic base remained `origin/main@6aeb26434724680c6da2162cd3544031b5a93f03`
  while this closeout ran, so the integrated release bump was cut from that
  verified mainline state.
- Another local worktree owns a dirty `main` branch, so the final integration is
  pushed directly from this verified workstream branch to `origin/main` instead
  of mutating that unrelated checkout.
- The final `origin/main` promotion uses the governed `skip_remote_gate` waiver
  recorded in
  `receipts/gate-bypasses/20260414T071925Z-codex-ws-0368-main-publish-r4-b8a2a0d-skip-remote-gate.json`
  because clean `origin/main@6aeb26434724680c6da2162cd3544031b5a93f03` still
  reproduces the untouched whole-repo `ansible-lint` fatal baseline, while the
  ws-0368 branch-local regressions were revalidated locally from this publish
  worktree before the push.
