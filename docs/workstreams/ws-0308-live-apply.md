# Workstream ws-0308-live-apply: Live Apply ADR 0308 From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md)
- Title: Live apply the operator provisioning execution-surface and connectivity contract from latest `origin/main`
- Status: ready_for_merge
- Included In Repo Version: pending main integration
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Live Applied In Platform Version: 0.130.85
- Branch: `codex/ws-0308-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0308-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0108-operator-onboarding-and-offboarding`
- Conflicts With: `ws-0307-0308-operator-adrs`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-live-apply.md`, `docs/adr/0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning.md`, `docs/runbooks/operator-onboarding.md`, `docs/adr/.index.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `config/workflow-catalog.json`, `config/windmill/scripts/gate-status.py`, `scripts/gate_status.py`, `scripts/preflight_controller_local.py`, `scripts/workflow_catalog.py`, `platform/repo.py`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `tests/test_preflight_controller_local.py`, `tests/test_controller_automation_toolkit.py`, `tests/test_common_docker_bridge_chains_helper.py`, `tests/test_docker_runtime_role.py`, `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-*`

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

- The latest synchronized base is `origin/main` commit `a2f2ea16d24504a9bb4015a86db20761e1be66db`, which carried repository version `0.177.136` and platform version `0.130.85`; the exact-main replay source after rebasing this workstream is commit `b97c0d5bc20619229829525d49a7e07f6a48ebbf`.
- `make preflight WORKFLOW=operator-onboard` passed on the exact-main tree, with Keycloak discovery, the private OpenBao mTLS listener, and the private Windmill API all returning healthy results in `receipts/live-applies/evidence/2026-04-02-ws-0308-preflight-r2-0.177.136.txt`.
- `uv run --with pytest python -m pytest -q tests/test_common_docker_bridge_chains_helper.py tests/test_docker_runtime_role.py::test_common_docker_bridge_chains_warms_control_socket_before_failing_safe tests/test_controller_automation_toolkit.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_operator_manager.py tests/test_preflight_controller_local.py` passed with `45 passed in 3.09s`, recorded in `receipts/live-applies/evidence/2026-04-02-ws-0308-pytest-r4-0.177.136.txt`.
- The first exact-main `make converge-windmill env=production` replay failed truthfully in `receipts/live-applies/evidence/2026-04-02-ws-0308-converge-windmill-r3-0.177.136.txt` when the shared Docker bridge-chain assertion evaluated stale post-retry state and reported `Docker is running but the nat DOCKER chain is missing; published ports will fail.` even after the retry loop had recovered the chain.
- After refreshing the final nat and forward probes in `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, the exact-main `make converge-windmill env=production` replay passed in `receipts/live-applies/evidence/2026-04-02-ws-0308-converge-windmill-r4-0.177.136.txt` with final recaps `docker-runtime-lv3 ok=331 changed=45 failed=0`, `postgres-lv3 ok=93 changed=2 failed=0`, and `proxmox_florin ok=41 changed=4 failed=0`.
- The exact-main Windmill dry run succeeded against `f/lv3/operator_onboard` and preserved the generated state path plus roster path in `receipts/live-applies/evidence/2026-04-02-ws-0308-windmill-dry-run-r3-0.177.136.txt`.
- The controller-local fallback path now works from this isolated worktree after `platform/repo.py` learned how to resolve shared `.local` assets from the parent repository root; the successful proof is `receipts/live-applies/evidence/2026-04-02-ws-0308-controller-fallback-r3-0.177.136.txt`.
- `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate` passed in `receipts/live-applies/evidence/2026-04-02-ws-0308-live-apply-receipts-validate-r1-0.177.136.txt`, and `./scripts/validate_repo.sh agent-standards` passed in `receipts/live-applies/evidence/2026-04-02-ws-0308-agent-standards-r1-0.177.136.txt`.
- The first branch-local `make validate` replay caught a real registry issue rather than an ADR 0308 code bug: `receipts/live-applies/evidence/2026-04-02-ws-0308-validate-r1-0.177.136.txt` showed ADR 0308 still claimed as an exclusive surface in multiple active workstreams. After converting the shared platform surfaces to shared-contract ownership and adding the generated manifest/diagram surfaces, `receipts/live-applies/evidence/2026-04-02-ws-0308-workstream-surfaces-r3-0.177.136.txt` passed and `receipts/live-applies/evidence/2026-04-02-ws-0308-validate-r2-0.177.136.txt` reduced the remaining local failure to the intentional pre-release canonical-truth delta on `changelog.md`.
- `make remote-validate` first surfaced stale generated artifacts, then passed cleanly on `receipts/live-applies/evidence/2026-04-02-ws-0308-remote-validate-r3-0.177.136.txt` after `build/platform-manifest.json` and `docs/diagrams/agent-coordination-map.excalidraw` were refreshed from source.
- `make pre-push-gate` passed every lane except `generated-docs`, and both the remote primary and the local fallback agreed that the only remaining branch-local blocker is the intentional pending-release canonical-truth update on `changelog.md`; see `receipts/live-applies/evidence/2026-04-02-ws-0308-pre-push-gate-r1-0.177.136.txt`.
- `git diff --check` passed cleanly in `receipts/live-applies/evidence/2026-04-02-ws-0308-git-diff-check-r1-0.177.136.txt`.

## Results

- ADR 0308 is live on platform version `0.130.85`, and the branch now records the correct operator provisioning execution surface, network topology, and operator runbook for future agents.
- Operator-onboard preflight now fails closed on real dependency outages by checking Keycloak discovery, the private OpenBao listener, and the Windmill API before the workflow starts.
- The Windmill gate-status path and controller-local fallback now resolve the real worker path and local secret checkout shape from either the repo root or a detached git worktree.
- The exact-main replay also hardened a shared runtime guard by re-probing Docker chain state after the retry loop, eliminating a false failure that latest `origin/main` exposed during the Windmill converge.
- The repo automation bundle is now fully replayed on the branch: remote validation is green, and the only branch-local pre-push failure still points at the protected `changelog.md` update that intentionally waits for merge-to-main.

## Merge-to-Main Notes

- Protected integration work still belongs to the final mainline step: bump `VERSION`, update `changelog.md`, refresh the top-level `README.md` status summary if the integrated truth changed, and update `versions/stack.yaml` only when the merge commit becomes the final verified canonical truth.
- The branch-local receipt `receipts/live-applies/2026-04-02-adr-0308-operator-provisioning-connectivity-live-apply.json` is the canonical audit trail for the live apply itself; the merge-to-main step should either promote it as the canonical receipt or cut a separate mainline receipt if the protected release write materially changes the final evidence set.
