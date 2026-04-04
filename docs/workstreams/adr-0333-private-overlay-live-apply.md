# Workstream ADR 0333: Private Overlay Live Apply

- ADR: [ADR 0333](../adr/0333-private-overlay-files-for-deployment-specific-secrets-and-identities.md)
- Title: finish the shared private-overlay bootstrap alias contract and verify it from a dedicated worktree
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0333-private-overlay-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0333-private-overlay-mainline-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: 0.130.98
- Latest Verified Base: `origin/main@972e3da17e7f9a7c87dc3e7979a38817d113c6f5` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0333-private-overlay`
- Worktree: `.worktrees/ws-0333-private-overlay`
- Owner: codex
- Depends On: `ADR 0034`, `ADR 0167`, `ADR 0268`, `ADR 0330`, `ADR 0333`
- Conflicts With: none

## Scope

- replace the remaining active controller-local bootstrap key contract with the
  generic shared-overlay alias under `.local/ssh/bootstrap.id_ed25519`
- make linked worktrees resolve and materialize shared `.local` files instead
  of creating shadow copies under `.worktrees/.../.local`
- verify the build-server validation path, controller preflight path, and the
  exact-main repo automation around this private-overlay contract

## Outcome

- `platform/repo.py`, `scripts/controller_automation_toolkit.py`, `scripts/drift_lib.py`, and the active controller-side helpers now resolve `.local/...` inputs against the shared checkout root instead of a nested worktree shadow.
- `scripts/materialize_bootstrap_key_alias.py` plus `config/worktree-bootstrap-manifests.json` now materialize the canonical `.local/ssh/bootstrap.id_ed25519` alias from older legacy bootstrap filenames so fresh worktrees can satisfy controller-local contracts without manual copying.
- Active bootstrap-key consumers now use the shared alias contract across the build-server config, workflow catalog, inventory defaults, role defaults, Windmill wrappers, and operator tooling, while `scripts/validation_runner_contracts.py` rejects absolute workstation paths and the old legacy key name in `config/build-server.json`.
- The workstream now declares and refreshes `docs/diagrams/agent-coordination-map.excalidraw` as a shared generated surface because the added active workstream entry changes the coordination map.
- The exact-main replay also adds ADR 0165 metadata headers to the changed collection role-default copies so the stricter current validator accepts the shared-overlay defaults on latest main.

## Verification

- Live controller proof passed from the dedicated worktree: `python3 scripts/materialize_bootstrap_key_alias.py`, `make preflight WORKFLOW=configure-edge-publication`, and `./scripts/remote_exec.sh check-build-server` all succeeded, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-bootstrap-alias-r1.json`, `receipts/live-applies/evidence/2026-04-04-adr-0333-preflight-configure-edge-publication-r1.txt`, and `receipts/live-applies/evidence/2026-04-04-adr-0333-check-build-server-r1.txt`.
- Focused ADR 0333 regression coverage passed after the remote-exec snapshot reuse fix: `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_materialize_bootstrap_key_alias.py tests/test_controller_automation_toolkit.py tests/test_preflight_controller_local.py tests/test_remote_exec.py tests/test_ephemeral_windmill_wrappers.py tests/test_provision_operator.py tests/test_validation_runner_contracts.py -q` returned `53 passed in 22.98s`, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-targeted-tests-r2.txt`.
- Repository automation validation passed on the rebased branch after the workstream-registry and diagram refreshes: `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models`, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-validate-repo-r4.txt`.
- The dependency-graph lane now passes on the branch with the regenerated coordination map, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-dependency-graph-r3.txt` and `receipts/live-applies/evidence/2026-04-04-adr-0333-diagrams-r1.txt`.
- `make remote-validate` reached the real remote builder first, then fell back locally; the final lane summary passed `agent-standards`, `workstream-surfaces`, `atlas-lint`, `policy-validation`, `iac-policy-scan`, `alert-rule-validation`, `type-check`, and `dependency-graph`, while the heavy fallback `ansible-syntax` and `schema-validation` lanes timed out, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-remote-validate-r3.txt`.
- The exact-main replay on `origin/main@972e3da17e7f9a7c87dc3e7979a38817d113c6f5` passed `80` focused pytest cases across the ADR 0333 and Atlas regression slice, `python3 scripts/live_apply_receipts.py --validate`, `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs generated-portals`, and the dependency-graph checks, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-mainline-targeted-tests-r4.txt`, `receipts/live-applies/evidence/2026-04-04-adr-0333-mainline-live-apply-receipts-r4.txt`, `receipts/live-applies/evidence/2026-04-04-adr-0333-mainline-validate-repo-r10.txt`, and `receipts/live-applies/evidence/2026-04-04-adr-0333-mainline-dependency-graph-r3.txt`.
- `make pre-push-gate` passed on the refreshed exact-main tree after the latest `origin/main` delta landed; the remote build-server run passed every lane except `atlas-lint`, where Atlas still timed out reaching the ephemeral Postgres host-gateway address, and the governed local fallback reran only `atlas-lint` successfully before merging the final gate status, preserved in `receipts/live-applies/evidence/2026-04-04-adr-0333-mainline-pre-push-gate-r3.txt`.

## Exact-Main Integration Status

- Exact-main canonical truth now records ADR 0333 in `README.md`, `changelog.md`, `versions/stack.yaml`, and `docs/status/history/live-apply-evidence.md` via the mainline receipt `2026-04-04-adr-0333-private-overlay-mainline-live-apply`.
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py status --json` still reports repository version `0.178.3`, platform version `0.130.98`, `0 workstreams in progress`, and a blocked numbered release cut only because three unrelated `controller_dependency_gap` waiver blockers remain open through `2026-04-06`.
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --dry-run` shows the next candidate repository release would be `0.178.4` once those unrelated blockers clear.
- Because the global release manager remains blocked outside this ADR, `Included In Repo Version` remains `not yet` even though the exact-main merge, canonical receipt, and full pre-push replay are complete.
