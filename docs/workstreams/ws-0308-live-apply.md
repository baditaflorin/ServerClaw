# Workstream ws-0308-live-apply: Live Apply ADR 0308 From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md)
- Title: Live apply the operator provisioning execution-surface and connectivity contract from latest `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.138
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Live Applied In Platform Version: 0.130.85
- Latest Verified Base: `origin/main@16280d12a34e722926e452886bcc40642b70cc09` (`repo 0.177.137`, `platform 0.130.86`)
- Branch: `codex/ws-0308-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0308-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0108-operator-onboarding-and-offboarding`
- Conflicts With: `ws-0307-0308-operator-adrs`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-live-apply.md`, `docs/adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md`, `docs/runbooks/operator-onboarding.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `config/workflow-catalog.json`, `config/windmill/scripts/gate-status.py`, `scripts/gate_status.py`, `scripts/preflight_controller_local.py`, `scripts/workflow_catalog.py`, `platform/repo.py`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `tests/test_preflight_controller_local.py`, `tests/test_controller_automation_toolkit.py`, `tests/test_common_docker_bridge_chains_helper.py`, `tests/test_docker_runtime_role.py`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`, `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-*`

## Scope

- make the operator-onboard preflight fail closed on real dependency outages instead of only checking controller-local secrets
- align ADR 0308 and the operator onboarding runbook with the real Windmill path, token file, SSH proxy fallback, and controller-local OpenBao tunnel requirements
- replay the exact-main operator provisioning path from the latest synchronized `origin/main`, capture the first regression encountered, repair it in-repo, and preserve the live evidence needed for a safe mainline merge

## Non-Goals

- changing `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` before the protected mainline integration step
- widening operator provisioning beyond the existing Windmill `f/lv3/operator_onboard` and `operator_manager.py` flow
- changing Keycloak, OpenBao, or Windmill topology beyond the connectivity and verification contract recorded by ADR 0308

## Expected Repo Surfaces

- `docs/adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/workstreams/ws-0308-live-apply.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.138.md`
- `versions/stack.yaml`
- `workstreams.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `config/workflow-catalog.json`
- `config/windmill/scripts/gate-status.py`
- `scripts/gate_status.py`
- `scripts/preflight_controller_local.py`
- `scripts/workflow_catalog.py`
- `platform/repo.py`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `tests/test_preflight_controller_local.py`
- `tests/test_controller_automation_toolkit.py`
- `tests/test_common_docker_bridge_chains_helper.py`
- `tests/test_docker_runtime_role.py`
- `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`
- `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json`

## Expected Live Surfaces

- `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
- `https://100.64.0.1:8200` as the private OpenBao mTLS edge
- `http://100.64.0.1:8005/api/version` as the private Windmill API proxy
- the SSH proxy path from the controller through `ops@100.64.0.1` to `ops@10.10.10.20`
- the Windmill worker path `f/lv3/operator_onboard`

## Ownership Notes

- `ws-0307-0308-operator-adrs` already touched ADR 0308, so this workstream preserves only the latest exact-main truth and keeps the release-truth surfaces deferred until merge-to-main.
- `workstreams.yaml` and `docs/adr/.index.yaml` remain shared-contract files and must be refreshed in a merge-safe way.
- The exact-main replay surfaced a latest-main regression in the shared Docker bridge-chain assertion path; this workstream owns the repair and the focused tests that now pin it.

## Verification

- The workstream first replayed from synchronized `origin/main` commit `a2f2ea16d24504a9bb4015a86db20761e1be66db` (`repo 0.177.136`, `platform 0.130.85`), then rebased onto `origin/main` commit `16280d12a34e722926e452886bcc40642b70cc09` (`repo 0.177.137`, `platform 0.130.86`). The latest rebased exact-main replay source is commit `2592ab846fa95548e920eac10f28b17e0f818fae`.
- `make preflight WORKFLOW=operator-onboard` passed on the rebased exact-main tree, with Keycloak discovery, the private OpenBao mTLS listener, and the private Windmill API all returning healthy results in `receipts/live-applies/evidence/2026-04-02-ws-0308-preflight-r3-0.177.137.txt`.
- `uv run --with pytest python -m pytest -q tests/test_common_docker_bridge_chains_helper.py tests/test_docker_runtime_role.py::test_common_docker_bridge_chains_warms_control_socket_before_failing_safe tests/test_controller_automation_toolkit.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_operator_manager.py tests/test_preflight_controller_local.py` passed with `45 passed in 3.08s`, recorded in `receipts/live-applies/evidence/2026-04-02-ws-0308-pytest-r5-0.177.137.txt`.
- The first exact-main `make converge-windmill env=production` replay failed truthfully in `receipts/live-applies/evidence/2026-04-02-ws-0308-converge-windmill-r3-0.177.136.txt` when the shared Docker bridge-chain assertion evaluated stale post-retry state even after the retry loop had recovered the chain. After refreshing the final nat and forward probes in `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, the repaired replay passed on `0.177.136` in `receipts/live-applies/evidence/2026-04-02-ws-0308-converge-windmill-r4-0.177.136.txt`, and the rebased replay passed again on `0.177.137` in `receipts/live-applies/evidence/2026-04-02-ws-0308-converge-windmill-r5-0.177.137.txt` with final recaps `docker-runtime-lv3 ok=331 changed=46 failed=0`, `postgres-lv3 ok=93 changed=2 failed=0`, and `proxmox_florin ok=41 changed=4 failed=0`.
- The rebased exact-main Windmill dry run succeeded against `f/lv3/operator_onboard` and preserved the generated state path plus roster path in `receipts/live-applies/evidence/2026-04-02-ws-0308-windmill-dry-run-r4-0.177.137.txt`.
- The controller-local fallback path still works from this isolated worktree after `platform/repo.py` learned how to resolve shared `.local` assets from the parent repository root; the successful rebased proof is `receipts/live-applies/evidence/2026-04-02-ws-0308-controller-fallback-r4-0.177.137.txt`.
- The final branch-local closeout passed `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate` in `receipts/live-applies/evidence/2026-04-02-ws-0308-live-apply-receipts-validate-r4-0.177.137.txt`, `./scripts/validate_repo.sh agent-standards` in `receipts/live-applies/evidence/2026-04-02-ws-0308-agent-standards-r3-0.177.137.txt`, `./scripts/validate_repo.sh workstream-surfaces` in `receipts/live-applies/evidence/2026-04-02-ws-0308-workstream-surfaces-r5-0.177.137.txt`, and `git diff --check` in `receipts/live-applies/evidence/2026-04-02-ws-0308-git-diff-check-r4-0.177.137.txt`.
- `./scripts/validate_repo.sh generated-docs` still truthfully isolates the single branch-local pre-release delta on `changelog.md`; see `receipts/live-applies/evidence/2026-04-02-ws-0308-canonical-truth-check-r3-0.177.137.txt`.
- `make remote-validate` first surfaced stale generated truth in `receipts/live-applies/evidence/2026-04-02-ws-0308-remote-validate-r4-0.177.137.txt` after the new SBOM ownership surface landed. Refreshing `build/platform-manifest.json` and rerunning `scripts/generate_diagrams.py --write` in `receipts/live-applies/evidence/2026-04-02-ws-0308-platform-manifest-write-r2-0.177.137.txt` and `receipts/live-applies/evidence/2026-04-02-ws-0308-generate-diagrams-r2-0.177.137.txt` restored generated truth, and `receipts/live-applies/evidence/2026-04-02-ws-0308-remote-validate-r5-0.177.137.txt` then passed every remote lane.
- `make pre-push-gate` passed every heavy lane except `generated-docs`, including `ansible-lint`, `semgrep-sast`, `security-scan`, `generated-portals`, `packer-validate`, and `integration-tests`; both the remote primary path and the local fallback agreed that the only remaining branch-local blocker is the intentional pending-release canonical-truth update on `changelog.md`. See `receipts/live-applies/evidence/2026-04-02-ws-0308-pre-push-gate-r2-0.177.137.txt`.

## Results

- ADR 0308 is live on platform version `0.130.85`, and the branch now records the correct operator provisioning execution surface, network topology, and operator runbook for future agents.
- Operator-onboard preflight now fails closed on real dependency outages by checking Keycloak discovery, the private OpenBao listener, and the Windmill API before the workflow starts.
- The Windmill gate-status path and controller-local fallback now resolve the real worker path and local secret checkout shape from either the repo root or a detached git worktree.
- The exact-main replay also hardened a shared runtime guard by re-probing Docker chain state after the retry loop, eliminating a false failure that latest `origin/main` exposed during the Windmill converge.
- The branch now also records the refreshed `docker-runtime-lv3` SBOM snapshot in `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`, capturing the runtime state that the rebased exact-main converge validated.
- The repo automation bundle is now fully replayed on the branch: rebased `remote-validate` is green, and the only branch-local pre-push failure still points at the protected `changelog.md` update that intentionally waits for merge-to-main.

## Mainline Integration

- Repo version `0.177.138` is the protected mainline integration that promoted this workstream: `VERSION`, `changelog.md`, `docs/release-notes/0.177.138.md`, `docs/release-notes/README.md`, `README.md`, `versions/stack.yaml`, and `build/platform-manifest.json` were refreshed in the integrated tree.
- Platform version remains `0.130.86` because the release promoted already-live branch verification instead of representing a new live apply from `main`.
- The branch-local receipt `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json` is now the canonical latest receipt for this capability in `versions/stack.yaml`.
- The final integrated validation set passed `agent-standards`, `live_apply_receipts.py --validate`, `workstream-surfaces`, `generated-docs`, `git diff --check`, `make remote-validate`, and `make pre-push-gate`; see `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-agent-standards-r2-0.177.138.txt`, `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-live-apply-receipts-validate-r2-0.177.138.txt`, `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-workstream-surfaces-r2-0.177.138.txt`, `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-generated-docs-r2-0.177.138.txt`, `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-git-diff-check-r2-0.177.138.txt`, `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-remote-validate-r1-0.177.138.txt`, and `receipts/live-applies/evidence/2026-04-02-ws-0308-mainline-pre-push-gate-r1-0.177.138.txt`.
- The first release-manager write hit an Outline `collections.list` HTTP `502` during knowledge sync after the protected repo surfaces had already been written. The final integration used the built-in `LV3_SKIP_OUTLINE_SYNC=1` bypass to complete the release deterministically without changing the repo truth again.
